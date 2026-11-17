"""Marco 0.3.0 (ADR 0010 do oon-k8s-infra): as três Centrais são ecossistemas isolados.

Executa, sem rede nem credenciais, os passos reais do request-dev.yml que dependem
de qual Central atende o App: a resolução do endpoint e o código de App reservado.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

source = Path('.github/workflows/request-dev.yml').read_text()


def step_script(name):
    step = source.split(f'      - name: {name}\n', 1)[1].split('      - name:', 1)[0]
    return '\n'.join(line[10:] for line in step.split('        run: |\n', 1)[1].splitlines())


endpoint = step_script('Resolver endpoint canônico da Central')
centrals = ['central-ativacao', 'central-ativacao-hml', 'central-ativacao-dev']
cases = [(f'https://{host}.oonapps.online/api', f'https://{host}.oonapps.online/api') for host in centrals]
cases += [
    ('https://central-ativacao-hml.oonapps.online/api/', 'https://central-ativacao-hml.oonapps.online/api'),
    ('https://central-ativacao-hml.oonapps.online:443/api', 'https://central-ativacao-hml.oonapps.online/api'),
    ('', 'https://central-ativacao.oonapps.online/api'),
    ('https://central-ativacao-sandbox.oonapps.online/api', None),
    ('https://central-ativacao-hml.oonapps.online', None),
    ('http://central-ativacao-hml.oonapps.online/api', None),
    ('https://central-ativacao-hml.oonapps.online.evil.example/api', None),
    ('https://user:pass@central-ativacao-hml.oonapps.online/api', None),
    ('https://meus-apps-chml.oonapps.online/api', None),
]
for configured, expected in cases:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'output'
        summary = Path(directory) / 'summary'
        env = {
            **os.environ,
            'INPUT_ACTIVATION_API_URL': configured,
            'ORGANIZATION_ACTIVATION_API_URL': '',
            'DEFAULT_ACTIVATION_API_URL': 'https://central-ativacao.oonapps.online/api',
            'GITHUB_OUTPUT': str(output),
            'GITHUB_STEP_SUMMARY': str(summary),
        }
        result = subprocess.run(['bash', '-c', endpoint], env=env, capture_output=True, text=True)
        assert (result.returncode == 0) == (expected is not None), (configured, result.stderr)
        if expected:
            assert output.read_text().strip() == f'activation_api_url={expected}', output.read_text()
print(f'{len(cases)} request endpoint cases passed')

manifest = step_script('Validar contrato de publicação')
codes = [
    ('meus-apps', True),
    ('cdev-app', True),
    ('app-cdevx', True),
    ('app-cdev', False),
    ('app-chml', False),
    ('meus-apps-dev-cdev', False),
    # Bordas: o qualificador só é reservado como último segmento.
    ('cdev', True),
    ('chml', True),
    ('app-chml-v2', True),
    ('app-cdev-dev', True),
    ('app--chml', False),
    ('a-cdev', False),
]
for code, valid in codes:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'oon.deploy.json').write_text(json.dumps({'appCode': code, 'schemaVersion': '1'}))
        result = subprocess.run(['bash', '-c', manifest], cwd=directory,
                                env={**os.environ, 'GITHUB_OUTPUT': str(root / 'output')}, capture_output=True, text=True)
        assert (result.returncode == 0) == valid, (code, result.stderr)
        if not valid:
            assert 'sufixo reservado' in result.stderr, result.stderr
print(f'{len(codes)} reserved app code cases passed')

# Código fora do padrão (maiúsculas) é recusado pela validação geral, antes da
# conferência do sufixo reservado.
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'oon.deploy.json').write_text(json.dumps({'appCode': 'APP-CDEV', 'schemaVersion': '1'}))
    result = subprocess.run(['bash', '-c', manifest], cwd=directory,
                            env={**os.environ, 'GITHUB_OUTPUT': str(root / 'output')}, capture_output=True, text=True)
    assert result.returncode != 0 and 'appCode inválido' in result.stderr, result.stderr

# A recusa do código reservado acontece antes de qualquer token OIDC: o passo de
# validação vem antes do que pede o token, e só ele confere o sufixo.
validate_at = source.index('      - name: Validar contrato de publicação\n')
oidc_at = source.index('ACTIONS_ID_TOKEN_REQUEST_TOKEN')
assert validate_at < source.index('      - name: Resolver endpoint canônico da Central\n') < oidc_at
assert source.index('*-cdev || "$app_code" == *-chml') < oidc_at

# Endpoint vindo da variável da organização também aceita só as três Centrais.
for configured, ok in [
    ('https://central-ativacao-hml.oonapps.online/api', True),
    ('https://central-ativacao-dev.oonapps.online/api', True),
    ('https://central-ativacao-sandbox.oonapps.online/api', False),
    ('https://central-ativacao-chml.oonapps.online/api', False),
]:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'output'
        env = {
            **os.environ,
            'INPUT_ACTIVATION_API_URL': '',
            'ORGANIZATION_ACTIVATION_API_URL': configured,
            'DEFAULT_ACTIVATION_API_URL': 'https://central-ativacao.oonapps.online/api',
            'GITHUB_OUTPUT': str(output),
            'GITHUB_STEP_SUMMARY': str(Path(directory) / 'summary'),
        }
        result = subprocess.run(['bash', '-c', endpoint], env=env, capture_output=True, text=True)
        assert (result.returncode == 0) == ok, (configured, result.stderr)
        if ok:
            assert output.read_text().strip() == f'activation_api_url={configured}', output.read_text()
print('ecosystem order and organization endpoint cases passed')
