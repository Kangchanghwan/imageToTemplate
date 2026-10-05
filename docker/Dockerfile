FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir opencv-python-headless numpy pymupdf pdfplumber pillow scikit-image
WORKDIR /w
