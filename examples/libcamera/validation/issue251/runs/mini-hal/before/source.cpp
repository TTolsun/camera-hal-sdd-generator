#include "device/RequestManager.h"

namespace halcam {

RequestManager::RequestManager(const camera3_callback_ops_t *callbacks)
    : callbacks_(callbacks), thread_([this](Frame &f) { onFrame(f); }) {
    thread_.start();
}

RequestManager::~RequestManager() {
    drain();
    thread_.stop();
}

FrameFactory &RequestManager::selectFactory(const camera3_capture_request_t &request) {
    // Preview requests carry a single output buffer in this simplified model.
    if (request.num_output_buffers <= 1) {
        return previewFactory_;
    }
    return captureFactory_;
}

int RequestManager::submit(const camera3_capture_request_t &request) {
    FrameFactory &factory = selectFactory(request);
    std::unique_ptr<Frame> frame = factory.createFrame(request);
    Frame *raw = frame.get();
    {
        std::lock_guard<std::mutex> guard(lock_);
        inFlight_[request.frame_number] = std::move(frame);
    }
    if (!thread_.enqueue(raw)) {
        return -1;
    }
    return 0;
}

void RequestManager::onFrame(Frame &frame) {
    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)
                                            : static_cast<FrameFactory &>(captureFactory_);
    int ret = factory.runPipes(frame);
    if (ret == 0) {
        sendResult(frame);
    }
    onFrameDone(frame);
}

void RequestManager::sendResult(const Frame &frame) {
    camera3_capture_result_t result{};
    result.frame_number = frame.frameNumber;
    callbacks_->process_capture_result(callbacks_, &result);
}

void RequestManager::onFrameDone(Frame &frame) {
    std::lock_guard<std::mutex> guard(lock_);
    inFlight_.erase(frame.frameNumber);
}

void RequestManager::drain() {
    // Simplified: real code waits on a condition variable until inFlight_ is empty.
    std::lock_guard<std::mutex> guard(lock_);
    inFlight_.clear();
}

}  // namespace halcam
