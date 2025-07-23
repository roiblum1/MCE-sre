FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements-aggregator.txt .
RUN pip install --no-cache-dir -r requirements-aggregator.txt

# Copy aggregator code
COPY src/multi_cluster_aggregator.py .
COPY src/aggregator_main.py ./main.py

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose metrics port
EXPOSE 8080

# Run the aggregator
CMD ["python", "main.py"]