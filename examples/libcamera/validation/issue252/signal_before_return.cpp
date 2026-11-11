// Public libcamera-base probe, not a camera or hardware capture test.
#include <libcamera/base/object.h>
#include <libcamera/base/signal.h>
#include <libcamera/base/thread.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <sys/syscall.h>
#include <unistd.h>

using namespace libcamera;

namespace {
std::mutex mutex;
std::condition_variable changed;
std::atomic<bool> emitReturned{false};
bool finished, timedOut, beforeReturn, onReceiverThread;
long receiverTid;

class Receiver : public Object
{
public:
    void receive()
    {
        std::lock_guard<std::mutex> lock(mutex);
        beforeReturn = !emitReturned.load();
        onReceiverThread = Thread::current() == thread();
        receiverTid = syscall(SYS_gettid);
        finished = true;
        changed.notify_one();
    }
};

void waitForReceiver()
{
    std::unique_lock<std::mutex> lock(mutex);
    timedOut = !changed.wait_for(lock, std::chrono::seconds(5), [] { return finished; });
}

bool run(const char *name, ConnectionType type, bool expectedReceiverThread)
{
    finished = timedOut = beforeReturn = onReceiverThread = false;
    emitReturned = false;
    Thread worker;
    Receiver receiver;
    receiver.moveToThread(&worker);
    Signal<> signal;
    signal.connect(&receiver, &Receiver::receive, type);
    // A static slot executes synchronously. Its wait keeps emit() active until
    // the first receiver runs, without imposing a receiver-after-return order.
    signal.connect(&waitForReceiver);
    worker.start();
    const long senderTid = syscall(SYS_gettid);
    signal.emit();
    emitReturned = true;
    worker.exit();
    worker.wait();
    const bool passed = !timedOut && finished && beforeReturn &&
                        onReceiverThread == expectedReceiverThread &&
                        (receiverTid != senderTid) == expectedReceiverThread;
    std::cout << "{\"mode\":\"" << name << "\",\"passed\":" << (passed ? "true" : "false")
              << ",\"receiver_before_emit_return\":" << (beforeReturn ? "true" : "false")
              << ",\"on_receiver_thread\":" << (onReceiverThread ? "true" : "false")
              << ",\"sender_tid\":" << senderTid << ",\"receiver_tid\":" << receiverTid
              << ",\"gate_timeout\":" << (timedOut ? "true" : "false") << "}\n";
    return passed;
}
}

int main()
{
    bool passed = run("auto-other-thread", ConnectionTypeAuto, true);
    passed &= run("explicit-queued", ConnectionTypeQueued, true);
    passed &= run("explicit-direct-other-affinity", ConnectionTypeDirect, false);
    return passed ? 0 : 1;
}
