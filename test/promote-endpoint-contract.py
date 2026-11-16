"""Execute the promotion workflow's endpoint validation step without network or credentials."""
import os
from pathlib import Path
import subprocess

source = Path('.github/workflows/promote-environment.yml').read_text()
marker = '      - name: Validar endpoint da Central\n'
steps = source.split(marker)[1:]
# Um por job: o que promove e o que registra a falha também emitem OIDC para a URL.
assert len(steps) == 2, len(steps)
scripts = []
for step in steps:
    body = step.split('      - name:', 1)[0]
    scripts.append('\n'.join(line[10:] for line in body.split('        run: |\n', 1)[1].splitlines()))
assert scripts[0] == scripts[1], 'os dois jobs devem validar o endpoint da mesma forma'
# A validação precede qualquer credencial ou chamada: é a primeira etapa de cada job.
for job in ('  promote:\n', '  report-failure:\n'):
    first = source.split(job, 1)[1].split('    steps:\n', 1)[1].splitlines()[0]
    assert first == marker.rstrip('\n'), (job, first)

cases = [
    ('https://central-ativacao.oonapps.online/api', True),
    ('https://central-ativacao.oonapps.online/api/', True),
    ('https://central-ativacao-dev.oonapps.online/api', True),
    ('https://central-ativacao.oonapps.online:443/api', True),
    ('https://central-ativacao-hml.oonapps.online/api', False),
    ('http://central-ativacao.oonapps.online/api', False),
    ('https://central-ativacao.oonapps.online', False),
    ('https://central-ativacao.oonapps.online/api/x', False),
    ('https://central-ativacao.oonapps.online:8443/api', False),
    ('https://user:pass@central-ativacao.oonapps.online/api', False),
    ('https://central-ativacao.oonapps.online/api?x=1', False),
    ('https://central-ativacao.oonapps.online/api#x', False),
    ('https://central-ativacao.oonapps.online.evil.example/api', False),
    ('https://evil.example/api', False),
    ('https://central-ativacao.oonapps.online@evil.example/api', False),
    ('https://evil.example/https://central-ativacao.oonapps.online/api', False),
    (' https://central-ativacao.oonapps.online/api', False),
    ('https://central-ativacao.oonapps.online/api\nx', False),
    ('', False),
]
for url, valid in cases:
    result = subprocess.run(['bash', '-c', scripts[0]], env={**os.environ, 'ACTIVATION_API_URL': url}, capture_output=True, text=True)
    assert (result.returncode == 0) == valid, (url, result.returncode, result.stderr)
print(f'{len(cases)} promotion endpoint cases passed')
