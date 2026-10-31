/* Genuine udmabuf export and bracketed CPU RW access. No memfd DMA fallback. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/dma-buf.h>
#include <linux/udmabuf.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted;
static void stop(int sig) { interrupted = sig; }

static void event(const char *name, long result, int error)
{
    printf("{\"event\":\"%s\",\"result\":%ld,\"errno\":%d}\n", name, result, error);
    fflush(stdout);
}

static double now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static int sync_cpu(int fd, uint64_t flags, double deadline, const char *point)
{
    struct dma_buf_sync sync = { .flags = flags };
    for (;;) {
        errno = 0;
        int ret = ioctl(fd, DMA_BUF_IOCTL_SYNC, &sync), error = errno;
        int retry = ret < 0 && (error == EINTR || error == EAGAIN) && !interrupted && now() < deadline;
        printf("{\"event\":\"%s\",\"result\":%d,\"errno\":%d,\"flags\":%llu,\"retry\":%s}\n",
               point, ret, error, (unsigned long long)flags, retry ? "true" : "false");
        fflush(stdout);
        if (!retry) return ret;
    }
}

int main(int argc, char **argv)
{
    if (argc > 3) return 2;
    const char *provider = argc >= 2 ? argv[1] : "/dev/udmabuf";
    int pause_after_start = argc == 3 && !strcmp(argv[2], "--pause-after-start");
    if (argc == 3 && !pause_after_start) return 2;
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    int device = -1, backing = -1, dma = -1, failed = 1, started = 0;
    size_t size = sysconf(_SC_PAGESIZE);
    unsigned char *mapping = MAP_FAILED;
    double deadline = now() + 10;
    errno = 0;
    device = open(provider, O_RDWR | O_CLOEXEC);
    printf("{\"event\":\"provider-open\",\"provider\":\"%s\",\"result\":%d,\"errno\":%d}\n", provider, device, errno);
    fflush(stdout);
    if (device < 0) goto cleanup;
    backing = memfd_create("issue211-udmabuf-backing", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    if (backing < 0 || ftruncate(backing, size) || fcntl(backing, F_ADD_SEALS, F_SEAL_SHRINK)) {
        event("backing-failed", -1, errno);
        goto cleanup;
    }
    struct udmabuf_create create = { .memfd = backing, .flags = UDMABUF_FLAGS_CLOEXEC, .size = size };
    errno = 0;
    dma = ioctl(device, UDMABUF_CREATE, &create);
    printf("{\"event\":\"allocate\",\"result\":%d,\"errno\":%d,\"backing_fd\":%d,\"dmabuf_fd\":%d,\"size\":%zu}\n",
           dma, errno, backing, dma, size);
    fflush(stdout);
    if (dma < 0) goto cleanup;
    errno = 0;
    mapping = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, dma, 0);
    event("mmap", mapping == MAP_FAILED ? -1 : 0, errno);
    if (mapping == MAP_FAILED) goto cleanup;
    if (sync_cpu(dma, DMA_BUF_SYNC_START | DMA_BUF_SYNC_RW, deadline, "sync-start")) goto cleanup;
    started = 1;
    if (pause_after_start) {
        while (!interrupted) pause();
        goto cleanup;
    }
    for (size_t i = 0; i < size; ++i) ((volatile unsigned char *)mapping)[i] = (i * 17 + 31) & 255;
    int matches = 1;
    uint64_t checksum = 0;
    for (size_t i = 0; i < size; ++i) {
        unsigned char value = ((volatile unsigned char *)mapping)[i];
        matches &= value == ((i * 17 + 31) & 255);
        checksum += value;
    }
    printf("{\"event\":\"cpu-access\",\"result\":%d,\"errno\":0,\"bytes\":%zu,\"checksum\":%llu}\n",
           matches ? 0 : -1, size, (unsigned long long)checksum);
    fflush(stdout);
    if (!matches || interrupted) goto cleanup;
    failed = 0;
cleanup:
    if (started && sync_cpu(dma, DMA_BUF_SYNC_END | DMA_BUF_SYNC_RW, now() + 2, "sync-end")) failed = 1;
    if (mapping != MAP_FAILED) {
        errno = 0; int ret = munmap(mapping, size); event("munmap", ret, errno); if (ret) failed = 1;
    }
    if (dma >= 0) {
        errno = 0; int ret = close(dma); event("close-dmabuf", ret, errno); if (ret) failed = 1;
    }
    if (backing >= 0) {
        errno = 0; int ret = close(backing); event("close-backing", ret, errno); if (ret) failed = 1;
    }
    if (device >= 0) {
        errno = 0; int ret = close(device); event("close-provider", ret, errno); if (ret) failed = 1;
    }
    return failed || interrupted ? 1 : 0;
}
