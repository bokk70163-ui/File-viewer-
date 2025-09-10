# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port the app runs on
EXPOSE 10000

# Define the command to run your app using Gunicorn
# Gunicorn is a production-ready web server.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "bot:server"]
