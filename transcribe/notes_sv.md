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

 
