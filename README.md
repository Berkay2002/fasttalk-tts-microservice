# Kokoro-TTS

Kokoro-TTS is a Text-to-Speech (TTS) project that uses Docker for easy setup and deployment. This project provides two ways to run the application:

1. **Pull the Docker image and run it (the easy way)**.
2. **Clone the Git repository, build the Docker image, and then run it**.

## Ways to Run

### Option 1: Pull the Docker Image and Run

You can directly pull the pre-built Docker image from the Docker registry and run it.

1. **Pull the Docker image**:
   ```bash
   docker pull karthik0967/kokoro-tts:v4
1. **Create a input folder with a input file with some text (input/input.txt)**:
   ```
   Hello, this text is to check kokoro tts
2. **Run** This starts the server
    ```bash
    docker run -d --name kokoro-tts -p 8003:8000 -v "$PWD/app:/app" -v "$PWD/input:/app/input" -v "$PWD/output:/app/output" karthik0967/kokoro-tts:v4
3. **Then Run** This starts the client
    ```bash
    docker exec -it kokoro-tts python client.py
### Option 2: Clone the Git Repository, Build the Docker Image, and Run

If you prefer to clone the repository, build the Docker image locally, and run it, follow these steps.

1. **Clone the Git repository**:
   You can clone the repository using either SSH or HTTPS.

   * **Using SSH**:

     ```bash
     git clone git@gitlab.liu.se:karra081/kokoro-tts.git
     ```

   * **Using HTTPS**:

     ```bash
     git clone https://gitlab.liu.se/karra081/kokoro-tts.git
     ```

2. **Navigate to the project root**:

   ```bash
   cd kokoro-tts
   ```

3. **Build the Docker image**:
   Replace `<tag>` with the tag you want to assign to the image (e.g., `v4`).

   ```bash
   docker build -t kokoro-tts:<tag> .
   ```

4. **Create the `input` folder and `input.txt` file outside the app/**:
   Put the text you want the TTS system to process.

   Example:

   ```
   Hello, this is a sample text-to-speech conversion.
   ```

5. **Run the Docker container** (This starts the Server):
   Run the Docker container using the following command:

   ```bash
   docker run -d --name kokoro-tts -p 8003:8000 -v "$PWD/app:/app" -v "$PWD/input:/app/input" -v "$PWD/output:/app/output" kokoro-tts:v4
   ```

6. **Then Run** This starts the client
    ```bash
    docker exec -it kokoro-tts python client.py
   ```

   This command:

   * Runs the container in detached mode (`-d`).
   * Maps port 8000 inside the container to port 8003 on your machine.
   * Mounts the `app`, `input`, and `output` directories from your local machine to the container.

6. **Access the TTS service**:
   You can now interact with the TTS service on `localhost:8003` or using any HTTP client to send requests.

---

## Prerequisites

* **Docker** must be installed on your machine. You can download it from [here](https://www.docker.com/get-started).
* Clone the repository if you're building the image manually.

## File Structure

* `input/`: Folder where you put the `input.txt` file with text to convert to speech.
* `output/`: Folder where the generated audio file will be saved.

---





