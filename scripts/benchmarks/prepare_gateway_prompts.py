"""Prepare immutable, tokenizer-bounded prose inputs for exact gateway calibration."""
import argparse
import hashlib
import json
from pathlib import Path

from gufo_prompts import TASKS, synthetic_text


SIZES=(512,2048,8192,16384)


def build_prompt(size, tokenizer):
    if size not in SIZES:
        raise ValueError('Unreviewed cold input length')
    instruction=TASKS['story']
    room=size-128-len(tokenizer.encode(instruction,add_special_tokens=False).ids)
    if room<=0:
        raise ValueError('No capacity for prose')
    corpus=synthetic_text(20261002,size*2)
    ids=tokenizer.encode(corpus,add_special_tokens=False).ids
    if len(ids)<room:
        raise ValueError('Generated prose too short')
    while room>0:
        text=tokenizer.decode(ids[:room],skip_special_tokens=False)+instruction
        if len(tokenizer.encode(text,add_special_tokens=False).ids)<=size-128:
            return text
        room-=1
    raise ValueError('Cannot retain the prose instruction')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tokenizer',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from tokenizers import Tokenizer
    tokenizer=Tokenizer.from_file(str(args.tokenizer))
    args.output.mkdir(parents=True,exist_ok=False)
    manifest={'tokenizer_sha256':hashlib.sha256(args.tokenizer.read_bytes()).hexdigest(),'prompts':{}}
    for size in SIZES:
        text=build_prompt(size,tokenizer)
        data=text.encode('utf-8')
        name=f'prompt-{size}-prose.txt'
        with (args.output/name).open('xb') as stream:stream.write(data)
        manifest['prompts'][str(size)]={'file':name,'sha256':hashlib.sha256(data).hexdigest(),
            'text_tokens':len(tokenizer.encode(text,add_special_tokens=False).ids)}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('Wrote bounded prompt text; gateway calibrates and validates actual chat token counts.')


if __name__=='__main__':main()
