1. extrahera ut ljud till mp3
Python script som anropar vlc

2. extrahera ut unika bilder/frames ur film och när i filmen de visas
Python script som använder ffmpeg 

3. Transcription av mp3 från steg 1
Pyhthon script som plockar ut chunks baserat på bilderna i steg 2 och skickar till Berget.ai (KB-whisper) för transcription
Så varje bild av sin text

4. Beräkna vektoror för varje text chunk från steg 3
Python script som använder embedded modell hos Berget.ai
Resultat sparat i Postgresql + extension pgvector för lagring o matchning av vektorer

 
1:
uv run extract_audio.py ~/skogskurs/andreas_redin_skogsbruksplan.mp4

2:
uv run extract_frames.py ~/skogskurs/andreas_redin_skogsbruksplan.mp4

3: 
uv run remote.py ./output/audio/Tall.mp3

4:
uv run embed_chunks.py "output/Tall_transcribed.json" --course-id "skogskurs"   --presentation-id "tall" --replace-source

all:
uv run transcribe_pipeline.py ~/skogskurs/andreas_redin_skogsbruksplan.mp4 --course-id "skogskurs"   --presentation-id "tall" --replace-source


uv run search_chunks.py "kasksakjkjsakjsakjsakjsaassa" --course-id "skogskurs" --min-similarity=0.7

------------------------------------------------------------------------------------------------------------

