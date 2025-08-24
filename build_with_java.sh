#!/bin/bash

# Set up Java environment for Tika
export JAVA_HOME="/opt/homebrew/opt/openjdk"
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# Set up optimal environment variables
export KMP_DUPLICATE_LIB_OK="TRUE"
export TIKA_CLIENT_ONLY="False"
export TIKA_SERVER_TIMEOUT="60"
export TIKA_CLIENT_TIMEOUT="60"
export TIKA_STARTUP_TIMEOUT="120"
export TIKA_OCR_STRATEGY="no_ocr"
export JAVA_OPTS="-Xmx2g -XX:+UseG1GC"

echo "🚀 Starting knowledge base build with proper Java environment..."
echo "Java version: $(java -version 2>&1 | head -1)"
echo "Environment ready!"

# Run the build script
python scripts/build_knowledge_base.py --config config/repositories.yml --articles-config config/articles.yml --dirty

echo "✅ Build complete!"
