FROM sheetparser:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir onnxruntime pyclipper shapely paddle2onnx
