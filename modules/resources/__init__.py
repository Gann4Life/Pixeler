from playsound import playsound

class Audio:
    def play(audio_name : str, block : bool = True):
        '''Plays an audio file under .\\resources\\audio\\'''
        playsound(f'resources/audio/{audio_name}', block)

    def play_error(block : bool = True):
       Audio.play("sfx Error.mp3", block)

    def play_ding(block : bool = True):
        Audio.play("sfx Success.mp3", block)

    def play_xpop(block : bool = True):
        Audio.play("sfx XPop.mp3", block)

    def play_ypop(block : bool = True):
        Audio.play("sfx YPop.mp3", block)