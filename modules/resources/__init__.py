from playsound import playsound

class Audio:
    def play(audio_name : str, block : bool = True):
        '''Plays an audio file under .\\resources\\audio\\'''
        playsound(f'resources/audio/{audio_name}', block)

    def play_error(block : bool = True):
       Audio.play("error.mp3", block)

    def play_ding(block : bool = True):
        Audio.play("ding.mp3", block)

    def play_xpop(block : bool = True):
        Audio.play("xpop.wav", block)

    def play_ypop(block : bool = True):
        Audio.play("ypop.wav", block)