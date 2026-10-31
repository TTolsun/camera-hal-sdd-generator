#!/bin/bash
set -eu
source="$HOME/.cache/camera-hal-sdd-issue193-293/source"
build="$source/build-followup"
git -C "$source" rev-parse HEAD
git -C "$source" status --porcelain --untracked-files=no
git -C "$source" ls-remote origin HEAD
git -C "$source" show HEAD:src/apps/cam/camera_session.cpp
git -C "$source" show HEAD:src/libcamera/dma_buf_allocator.cpp
meson configure "$build"
sha256sum "$build/src/apps/cam/cam" "$build/src/libcamera/libcamera.so" "$build/src/libcamera/base/libcamera-base.so"
file "$build/src/apps/cam/cam"
ldd "$build/src/apps/cam/cam"
env LIBCAMERA_PIPELINES_MATCH_LIST=virtual "$build/src/apps/cam/cam" --camera Virtual2 --capture=3 --stream role=video,width=400,height=300,pixelformat=NV12
