"""Read the host's Voxtype settings; adapt its daemon text stage for file mode.

Text behavior follows Voxtype v0.6.0 src/text/mod.rs and
src/output/post_process.rs. These are explicit configured substitutions, not
inferred language cleanup. Desktop output/hotkey actions are never executed.
"""
import os
from pathlib import Path
import re
import subprocess
import tomllib

class SettingsError(ValueError):
    pass

def default_config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'voxtype'/'config.toml'

def read_settings(path):
    try:
        source=Path(path).read_text()
        settings=tomllib.loads(source)
    except (OSError,tomllib.TOMLDecodeError) as error:
        raise SettingsError('Could not load the existing Voxtype configuration') from error
    engine=settings.get('engine','whisper')
    local_engines={'whisper','parakeet','moonshine','sensevoice','paraformer','dolphin','omnilingual'}
    if engine not in local_engines:
        raise SettingsError('Private Flow requires a supported local Voxtype engine')
    whisper=settings.get('whisper',{})
    if engine=='whisper' and whisper.get('mode',whisper.get('backend','local'))!='local':
        raise SettingsError('Voxtype is configured for remote processing; Private Flow requires local transcription')
    return source,settings

# Same fixed spoken-punctuation vocabulary/order as Voxtype v0.6.0.
_PUNCTUATION=[
 ('question mark','?'),('exclamation mark','!'),('exclamation point','!'),
 ('open parenthesis','('),('close parenthesis',')'),('open paren','('),('close paren',')'),
 ('open bracket','['),('close bracket',']'),('open brace','{'),('close brace','}'),
 ('at sign','@'),('at symbol','@'),('dollar sign','$'),('percent sign','%'),
 ('plus sign','+'),('equals sign','='),('forward slash','/'),('single quote',"'"),
 ('double quote','"'),('new paragraph','\n\n'),('new line','\n'),
 ('period','.'),('comma',','),('colon',':'),('semicolon',';'),('dash','-'),('hyphen','-'),
 ('underscore','_'),('hash','#'),('hashtag','#'),('percent','%'),('ampersand','&'),
 ('asterisk','*'),('plus','+'),('equals','='),('slash','/'),('backslash','\\'),
 ('pipe','|'),('tilde','~'),('backtick','`'),('tab','\t'),
]

def replace_phrase(text,phrase,replacement):
    return re.sub(r'\b'+re.escape(phrase)+r'\b',lambda _:replacement,text,flags=re.IGNORECASE)

def apply_text_settings(text,settings):
    options=settings.get('text',{})
    if options.get('spoken_punctuation',False):
        for phrase,symbol in _PUNCTUATION:
            text=replace_phrase(text,phrase,symbol)
        for punctuation in '.,?!:;)]}':
            text=text.replace(' '+punctuation,punctuation)
        for punctuation in '([{':
            text=text.replace(punctuation+' ',punctuation).replace(' '+punctuation,punctuation)
        for symbol in '#@$':
            text=text.replace(' '+symbol,symbol).replace(symbol+' ',symbol)
        for symbol in '\n\t':
            text=text.replace(' '+symbol,symbol).replace(symbol+' ',symbol)
    for phrase,replacement in options.get('replacements',{}).items():
        text=replace_phrase(text,phrase.lower(),replacement)
    post=settings.get('output',{}).get('post_process') or {}
    command=post.get('command')
    if command:
        # Trusted host-configured command; transcript is stdin, never shell code.
        try:
            result=subprocess.run(['sh','-c',command],input=text,capture_output=True,
                                  text=True,timeout=post.get('timeout_ms',30000)/1000)
            if result.returncode==0 and result.stdout.strip():
                text=result.stdout.strip()
        except (OSError,subprocess.TimeoutExpired,UnicodeError):
            pass  # Match Voxtype's fallback to the original text on hook failure.
    return text
