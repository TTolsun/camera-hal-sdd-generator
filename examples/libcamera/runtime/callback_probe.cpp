// SPDX-License-Identifier: MIT
// Source-pinned public libcamera virtual-pipeline callback observation.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <libcamera/libcamera.h>
#include <libcamera/base/event_dispatcher.h>
#include <libcamera/base/object.h>
#include <libcamera/base/thread.h>
#include <libcamera/base/timer.h>
#include <libcamera/fence.h>
#include <libcamera/formats.h>
#include <sys/eventfd.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <atomic>
#include <chrono>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace libcamera;
using namespace std::chrono_literals;

static std::mutex outputMutex;
static std::atomic<unsigned int> returned{0};
static std::atomic<bool> stopping{false};
static unsigned int ordinal = 0;
static long tid() { return syscall(SYS_gettid); }
static void event(const std::string &kind, const std::string &fields = "")
{
    std::lock_guard<std::mutex> guard(outputMutex);
    auto now = std::chrono::steady_clock::now().time_since_epoch();
    std::cout << "{\"index\":" << ordinal++ << ",\"ns\":"
              << std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()
              << ",\"tid\":" << tid() << ",\"event\":\"" << kind << "\""
              << fields << "}" << std::endl;
}
static void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

class Observer : public Object {
public:
    explicit Observer(const std::string &connection) : connection_(connection), owner_(tid()) {}
    void complete(Request *request)
    {
        std::string data = ",\"connection\":\"" + connection_ + "\",\"cookie\":"
            + std::to_string(request->cookie()) + ",\"sequence\":" + std::to_string(request->sequence())
            + ",\"status\":" + std::to_string(request->status())
            + ",\"receiver_tid\":" + std::to_string(owner_)
            + ",\"affinity_match\":" + (Thread::current() == thread() ? "true" : "false")
            + ",\"inside_stop\":" + (stopping.load() ? "true" : "false");
        event("callback-enter", data);
        event("callback-return", data);
        returned.fetch_add(1);
    }
    void buffer(Request *request, FrameBuffer *buffer)
    {
        event("buffer", ",\"cookie\":" + std::to_string(request->cookie())
              + ",\"status\":" + std::to_string(buffer->metadata().status));
    }
private:
    std::string connection_;
    long owner_;
};

static void drain(unsigned int expected)
{
    Timer limit;
    limit.start(5s);
    while (returned.load() < expected && limit.isRunning())
        Thread::current()->eventDispatcher()->processEvents();
    limit.stop();
    require(returned.load() == expected, "callback count/timeout");
}

int main()
{
    try {
        event("probe-start", ",\"buffer_kind\":\"application-memfd-CPU-only\"");
        CameraManager manager;
        require(manager.start() == 0, "manager start");
        auto camera = manager.get("Virtual2");
        require(bool(camera), "Virtual2 unavailable");
        require(camera->acquire() == 0, "camera acquire");
        auto config = camera->generateConfiguration({StreamRole::VideoRecording});
        require(bool(config) && config->size() == 1, "configuration");
        auto &cfg = config->at(0);
        cfg.size = {400, 300};
        cfg.pixelFormat = formats::NV12;
        require(config->validate() != CameraConfiguration::Invalid, "validate");
        require(cfg.pixelFormat == formats::NV12, "NV12 unavailable");
        require(cfg.size == Size(400, 300), "400x300 unavailable");
        require(camera->configure(config.get()) == 0, "configure");
        Observer automatic("auto"), direct("direct"), queued("queued");
        camera->requestCompleted.connect(&automatic, &Observer::complete, ConnectionTypeAuto);
        camera->requestCompleted.connect(&direct, &Observer::complete, ConnectionTypeDirect);
        camera->requestCompleted.connect(&queued, &Observer::complete, ConnectionTypeQueued);
        camera->bufferCompleted.connect(&direct, &Observer::buffer, ConnectionTypeDirect);
        event("connections", ",\"receiver_affinity\":\"main thread, no moveToThread\"");

        for (int phase = 0; phase < 2; ++phase) {
            std::vector<std::unique_ptr<FrameBuffer>> buffers;
            std::vector<std::unique_ptr<Request>> requests;
            std::vector<SharedFD> allocations;
            require(camera->start() == 0, "camera start");
            event("capture-start", ",\"phase\":" + std::to_string(phase));
            for (unsigned int i = 0; i < 4; ++i) {
                int fd = memfd_create("libcamera-public-callback-probe", MFD_CLOEXEC);
                require(fd >= 0 && ftruncate(fd, cfg.frameSize) == 0, "memfd allocation");
                SharedFD shared{UniqueFD(fd)};
                unsigned int y = cfg.stride * cfg.size.height;
                std::vector<FrameBuffer::Plane> planes{{shared, 0, y}, {shared, y, cfg.frameSize-y}};
                buffers.push_back(std::make_unique<FrameBuffer>(planes));
                auto request = camera->createRequest(100 + phase * 100 + i);
                require(bool(request), "create request");
                std::unique_ptr<Fence> fence;
                if (phase == 1) {
                    int fenceFd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
                    require(fenceFd >= 0, "eventfd acquire-fence test input");
                    fence = std::make_unique<Fence>(UniqueFD(fenceFd));
                }
                require(request->addBuffer(cfg.stream(), buffers.back().get(), std::move(fence)) == 0, "add buffer");
                event("queue", ",\"cookie\":" + std::to_string(request->cookie())
                      + ",\"unsignalled_test_fence\":" + (phase ? "true" : "false"));
                require(camera->queueRequest(request.get()) == 0, "queue request");
                requests.push_back(std::move(request));
                allocations.push_back(shared);
            }
            if (phase == 0) drain(12);
            else std::this_thread::sleep_for(20ms);
            stopping.store(true);
            event("stop-enter", ",\"phase\":" + std::to_string(phase));
            int ret = camera->stop();
            event("stop-return", ",\"phase\":" + std::to_string(phase) + ",\"ret\":" + std::to_string(ret));
            stopping.store(false);
            require(ret == 0, "camera stop");
            drain((phase + 1) * 12);
            for (unsigned int i = 0; i < requests.size(); ++i) {
                require(requests[i]->status() == (phase ? Request::RequestCancelled : Request::RequestComplete), "request outcome");
                event("request-outcome", ",\"cookie\":" + std::to_string(requests[i]->cookie())
                      + ",\"status\":" + std::to_string(requests[i]->status()));
            }
        }
        camera->requestCompleted.disconnect();
        camera->bufferCompleted.disconnect();
        require(camera->release() == 0, "release");
        camera.reset();
        manager.stop();
        event("probe-pass", ",\"scope\":\"callback-observation-only\",\"request_callbacks\":" + std::to_string(returned.load()));
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "PROBE FAILED: " << error.what() << std::endl;
        return 1;
    }
}
