import torch
from datasets import load_dataset
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
model_id = "KBLab/kb-whisper-large"

model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id, torch_dtype=torch_dtype, use_safetensors=True, cache_dir="cache"
)
model.to(device)
processor = AutoProcessor.from_pretrained(model_id)

pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    torch_dtype=torch_dtype,
    device=device,
)

generate_kwargs = {"task": "transcribe", "language": "sv"}
# Add return_timestamps=True for output with timestamps
res = pipe("gran.mp3", 
           chunk_length_s=30,
           generate_kwargs={"task": "transcribe", "language": "sv"})
print(res)
