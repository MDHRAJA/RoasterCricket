"""Read public server-rendered IPL page data without executing site scripts."""
import json
import re

def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

def next_objects(text):
    for script in re.findall(r'<script[^>]*>(.*?)</script>', text, re.S):
        marker = 'self.__next_f.push('
        if marker not in script:
            continue
        try:
            block = json.loads(script[script.index(marker)+len(marker):].rstrip(';)'))
        except (ValueError, TypeError):
            continue
        if len(block) < 2 or not isinstance(block[1], str):
            continue
        for line in block[1].splitlines():
            try:
                obj = json.loads(line.split(':', 1)[1])
            except (ValueError, IndexError):
                continue
            yield from walk(obj)

def squad_data(text):
    candidates = [x for x in next_objects(text) if isinstance(x, dict) and isinstance(x.get('squad'),dict) and x['squad'].get('players')]
    if not candidates:
        raise ValueError('No squad embedded in official page')
    return max(candidates, key=lambda x: len(x['squad']['players']))
