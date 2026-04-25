#!/bin/bash
cd "$(dirname "$0")"
swift build --disable-sandbox
if [ $? -eq 0 ]; then
    echo "Build successful. Launching app..."
    ./.build/debug/AcrossAgentsAssistantClient
else
    echo "Build failed!"
fi
