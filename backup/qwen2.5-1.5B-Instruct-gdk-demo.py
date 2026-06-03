import os
import tempfile
import warnings
import yaml
import torch
import soundfile as sf
import librosa
import spaces
import gradio as gr
from transformers import (
    AutoTokenizer, AutoModelForCausalLM,
    SpeechT5Processor, SpeechT5ForTextToSpeech, SpeechT5HifiGan,
    WhisperProcessor, WhisperForConditionalGeneration
)
from datasets import load_dataset

# Suppress minor backend/audio warnings in console logs
warnings.filterwarnings("ignore")

# ================== Configuration ==================
HUGGINGFACE_MODEL_ID = "HuggingFaceH4/Qwen2.5-1.5B-Instruct-gkd"
TORCH_DTYPE = torch.bfloat16
MAX_NEW_TOKENS = 512
DO_SAMPLE = True
TEMPERATURE = 0.7
TOP_K = 50
TOP_P = 0.95

TTS_MODEL_ID = "microsoft/speecht5_tts"
TTS_VOCODER_ID = "microsoft/speecht5_hifigan"
STT_MODEL_ID = "openai/whisper-small"

hf_token = os.environ.get("HF_TOKEN")

# ================== Eager Model Loading ==================
# We load the models globally onto the CPU during startup. This prevents
# downloading/loading models during active GPU sessions, avoiding timeouts
# and saving your dynamic ZeroGPU quota.
print("Loading tokenizer and LLM on CPU...")
try:
    tokenizer = AutoTokenizer.from_pretrained(HUGGINGFACE_MODEL_ID, token=hf_token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    llm_model = AutoModelForCausalLM.from_pretrained(
        HUGGINGFACE_MODEL_ID,
        torch_dtype=TORCH_DTYPE,
        token=hf_token
    ).eval()
    print("LLM loaded successfully.")
except Exception as e:
    print(f"Error loading LLM: {e}")
    tokenizer, llm_model = None, None

print("Loading TTS models on CPU...")
try:
    tts_processor = SpeechT5Processor.from_pretrained(TTS_MODEL_ID, token=hf_token)
    tts_model = SpeechT5ForTextToSpeech.from_pretrained(TTS_MODEL_ID, token=hf_token).eval()
    tts_vocoder = SpeechT5HifiGan.from_pretrained(TTS_VOCODER_ID, token=hf_token).eval()

    # Load speaker embeddings
    embeddings = load_dataset("Matthijs/cmu-arctic-xvectors", split="validation", token=hf_token)
    speaker_embeddings = torch.tensor(embeddings[7306]["xvector"]).unsqueeze(0)
    print("TTS models loaded successfully.")
except Exception as e:
    print(f"Error loading TTS: {e}")
    tts_processor, tts_model, tts_vocoder, speaker_embeddings = None, None, None, None

print("Loading Whisper on CPU...")
try:
    whisper_processor = WhisperProcessor.from_pretrained(STT_MODEL_ID, token=hf_token)
    whisper_model = WhisperForConditionalGeneration.from_pretrained(STT_MODEL_ID, token=hf_token).eval()
    print("Whisper loaded successfully.")
except Exception as e:
    print(f"Error loading Whisper: {e}")
    whisper_processor, whisper_model = None, None


# ================== UI & Configuration Helpers ==================
def generate_pretty_html(data):
    html = """
    <div class="font-sans max-w-xl mx-auto bg-gray-800 text-white rounded-lg p-6 shadow-md">
      <h2 class="text-xl font-semibold text-white border-b border-gray-600 pb-2 mb-4">Model Info</h2>
    """
    for key, value in data.items():
        html += f"""
        <div class="mb-3">
          <strong class="text-blue-400 inline-block w-40">{key}:</strong>
          <span class="text-gray-300">{value}</span>
        </div>
        """
    html += "</div>"
    return html


def load_config():
    if os.path.exists("config.yaml"):
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            pass
    # Fallback structure if config.yaml is missing or corrupted
    return {
        "LLM Model ID": HUGGINGFACE_MODEL_ID,
        "TTS Model ID": TTS_MODEL_ID,
        "STT Model ID": STT_MODEL_ID,
        "Torch Dtype": str(TORCH_DTYPE),
        "Max New Tokens": MAX_NEW_TOKENS,
        "Temperature": TEMPERATURE
    }


def render_modern_info():
    try:
        config = load_config()
        return generate_pretty_html(config)
    except Exception as e:
        return f"<div style='color: red;'>Error loading config: {str(e)}</div>"


def load_readme():
    if os.path.exists("README.md"):
        with open("README.md", "r", encoding="utf-8") as f:
            return f.read()
    return "### Qwen2.5 Voice Chatbot\nUpload audio or chat via text interface."


def split_text_into_chunks(text, max_chars=250):
    """
    Splits text safely for SpeechT5. Handles edge cases where single
    sentences are longer than max_chars by sub-chunking them on word limits.
    """
    processed_text = text.replace("...", ".").replace("e.g.", "eg").replace("i.e.", "ie")
    sentences = processed_text.split(". ")
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Handle sentences that exceed the maximum limit on their own
        if len(sentence) >= max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip() + ".")
                current_chunk = ""

            words = sentence.split(" ")
            temp_chunk = ""
            for word in words:
                if len(temp_chunk) + len(word) + 1 < max_chars:
                    temp_chunk += " " + word if temp_chunk else word
                else:
                    chunks.append(temp_chunk.strip() + ".")
                    temp_chunk = word
            if temp_chunk:
                current_chunk = temp_chunk
        else:
            if len(current_chunk) + len(sentence) + 2 < max_chars:
                current_chunk += ". " + sentence if current_chunk else sentence
            else:
                chunks.append(current_chunk.strip() + ".")
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip() + ".")

    return [c.replace("..", ".") for c in chunks if c.strip() and c != "."]


# ================== Chat & Audio Processing ==================
def user_interaction(user_message, history):
    """
    Appends user text instantly to the chat history and clears the textbox.
    """
    if not user_message or not user_message.strip():
        return "", history
    return "", history + [{"role": "user", "content": user_message}]


@spaces.GPU(duration=60)
def generate_response_and_audio(history):
    """
    Runs the inference models sequentially on the allocated GPU.
    """
    # Models loaded at module level; accessed read-only here

    if not history or history[-1].get("role") != "user":
        return history, None

    if tokenizer is None or llm_model is None:
        return history + [{"role": "assistant", "content": "Error: Models are not fully loaded."}], None

    # Dynamically move the globally defined models to GPU inside the active execution frame
    device = "cuda" if torch.cuda.is_available() else "cpu"
    llm_model.to(device)

    # Sanitize and structure message list for Chat Template conversion
    messages = []
    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role and content:
            messages.append({"role": role, "content": str(content)})

    try:
        input_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception as e:
        print(f"Chat template template conversion failed, applying fallback formatting: {e}")
        input_text = ""
        for item in messages[:-1]:
            input_text += f"{item['role'].capitalize()}: {item['content']}\n"
        input_text += f"User: {messages[-1]['content']}\nAssistant:"

    # 1. Text Generation
    try:
        inputs = tokenizer(input_text, return_tensors="pt", padding=True, truncation=True).to(device)
        with torch.no_grad():
            output_ids = llm_model.generate(
                inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=DO_SAMPLE,
                temperature=TEMPERATURE,
                top_k=TOP_K,
                top_p=TOP_P,
                pad_token_id=tokenizer.eos_token_id
            )
        input_length = inputs["input_ids"].shape[-1]
        generated_text = tokenizer.decode(output_ids[0][input_length:], skip_special_tokens=True).strip()
    except Exception as e:
        print(f"LLM Error: {e}")
        return history + [{"role": "assistant", "content": "Sorry, I encountered an issue processing that query."}], None

    # Update history container
    updated_history = history + [{"role": "assistant", "content": generated_text}]

    # 2. Text-to-Speech (TTS) Generation
    audio_path = None
    if None not in [tts_processor, tts_model, tts_vocoder, speaker_embeddings]:
        try:
            tts_model.to(device)
            tts_vocoder.to(device)
            spk_emb = speaker_embeddings.to(device)

            text_chunks = split_text_into_chunks(generated_text)
            full_speech = []

            for chunk in text_chunks:
                tts_inputs = tts_processor(text=chunk, return_tensors="pt", max_length=512, truncation=True).to(device)
                with torch.no_grad():
                    speech = tts_model.generate_speech(tts_inputs["input_ids"], spk_emb, vocoder=tts_vocoder)
                full_speech.append(speech.cpu())

            if full_speech:
                full_speech_tensor = torch.cat(full_speech, dim=0)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    audio_path = tmp_file.name
                    sf.write(audio_path, full_speech_tensor.numpy(), samplerate=16000)

        except Exception as e:
            print(f"TTS Error: {e}")

    return updated_history, audio_path


@spaces.GPU(duration=30)
def transcribe_audio(filepath):
    """
    Transcribes audio utilizing the Whisper-small architecture.
    """
    # Whisper models loaded at module level; accessed read-only here
    if filepath is None:
        return ""

    if whisper_model is None or whisper_processor is None:
        return "Whisper pipeline is not available."

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        whisper_model.to(device)

        audio, sr = librosa.load(filepath, sr=16000)
        inputs = whisper_processor(audio, sampling_rate=sr, return_tensors="pt")
        input_features = inputs.input_features.to(device)

        with torch.no_grad():
            outputs = whisper_model.generate(input_features)

        return whisper_processor.batch_decode(outputs, skip_special_tokens=True)[0]
    except Exception as e:
        return f"Transcription error: {e}"


# ================== Gradio UI Definition ==================
with gr.Blocks(head="""
    <script src="https://cdn.tailwindcss.com "></script>
""") as demo:
    gr.Markdown("""
    <div class="bg-gray-900 text-white p-4 rounded-lg shadow-md mb-6">
      <h1 class="text-2xl font-bold">Qwen2.5 Chatbot with Voice Input/Output</h1>
      <p class="text-gray-300">Powered by Gradio & Hugging Face ZeroGPU</p>
    </div>
    """)

    with gr.Tab("Chat"):
        gr.HTML("""
        <div class="bg-gray-800 p-4 rounded-lg mb-4">
          <label class="block text-gray-300 font-medium mb-2">Chat Interface</label>
        </div>
        """)
        chatbot = gr.Chatbot(type='messages', elem_classes=["bg-gray-800", "text-white"])
        text_input = gr.Textbox(
            placeholder="Type your message and press Enter...",
            label="User Input",
            elem_classes=["bg-gray-700", "text-white", "border-gray-600"]
        )
        audio_output = gr.Audio(label="Response Audio", autoplay=True)

        # Two-stage progressive submit pattern for fluid UX
        text_input.submit(
            fn=user_interaction,
            inputs=[text_input, chatbot],
            outputs=[text_input, chatbot],
            queue=False
        ).then(
            fn=generate_response_and_audio,
            inputs=[chatbot],
            outputs=[chatbot, audio_output]
        )

    with gr.Tab("Transcribe"):
        gr.HTML("""
        <div class="bg-gray-800 p-4 rounded-lg mb-4">
          <label class="block text-gray-300 font-medium mb-2">Audio Transcription</label>
        </div>
        """)
        audio_input = gr.Audio(type="filepath", label="Upload Audio or Record Voice")
        transcribed = gr.Textbox(
            label="Transcription",
            elem_classes=["bg-gray-700", "text-white", "border-gray-600"]
        )
        # Using .change() tracks both file uploads and microphone input completions
        audio_input.change(fn=transcribe_audio, inputs=audio_input, outputs=transcribed)

    clear_btn = gr.Button("Clear All", elem_classes=["bg-gray-600", "hover:bg-gray-500", "text-white", "mt-4"])
    clear_btn.click(lambda: ([], "", None), None, [chatbot, text_input, audio_output])

    html_output = gr.HTML("""
    <div class="bg-gray-800 text-white p-4 rounded-lg mt-6 text-center">
      Loading model info...
    </div>
    """)
    demo.load(fn=render_modern_info, outputs=html_output)


# ================== Execution ==================
if __name__ == "__main__":
    demo.queue().launch()
