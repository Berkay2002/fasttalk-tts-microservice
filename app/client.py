import asyncio
import websockets
import json
import os
import time

# Available voices
available_voices = {
    "1": "af_sarah",
    "2": "zf_xiaoxiao",
}

MAX_CHUNK_SIZE = 1000  # You can tune this based on what your server handles well


def split_text(text, chunk_size=MAX_CHUNK_SIZE):
    """Split large input text into smaller chunks."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


async def send_chunk(uri, chunk_text, voice, chunk_index):
    request = {
        "text": chunk_text,
        "lang": "en-us",
        "voice": voice,
        "speed": 1.0,
        "format": "wav"
    }

    try:
        async with websockets.connect(uri, ping_interval=30, ping_timeout=60) as websocket:
            await websocket.send(json.dumps(request))
            print(f"[Chunk {chunk_index}] Sent request.")

            async for message in websocket:
                data = json.loads(message)
                if data["status"] == "progress":
                    print(f"[Chunk {chunk_index}] Progress: {data['progress']*100:.1f}%")
                elif data["status"] == "ok":
                    print(f"[Chunk {chunk_index}] Audio generated: {data['file']} ({data['format']})")
                    break
                elif data["status"] == "error":
                    print(f"[Chunk {chunk_index}] Error: {data['message']}")
                    break
    except Exception as e:
        print(f"[Chunk {chunk_index}] Failed with error: {e}")


async def tts_client():
    uri = "ws://localhost:8003"

    # Load text input
    try:
        with open("input/input.txt", "r") as file:
            text = file.read()
    except FileNotFoundError:
        print("❌ Error: input/input.txt not found.")
        return

    # Show available voices
    print("Select a voice:")
    for key, value in available_voices.items():
        print(f"{key}: {value}")
    voice_choice = input("Enter the number of the voice you want to use: ")

    # Validate choice
    if voice_choice not in available_voices:
        print("Invalid choice. Please choose a valid voice number.")
        return
    voice = available_voices[voice_choice]

    # Split text if too long
    chunks = split_text(text)
    print(f"\nTotal chunks to process: {len(chunks)}")

    # Send each chunk separately
    for i, chunk in enumerate(chunks, start=1):
        await send_chunk(uri, chunk, voice, i)


if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(tts_client())
    end_time = time.time()
    print(f"\nTotal time taken: {end_time - start_time:.2f} seconds")
