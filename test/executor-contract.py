"""Contrato do executor da promoção (marco 0.3.0, I-2 da especificação do marco).

O promote-environment.yml não tem executor próprio: ele faz checkout de
`oondemand/central-ativacao@main` e roda `scripts/actions/deploy-central-dev.js`
de lá. Por isso a ordem de merge importa (ver "Ordem de merge" no README): o que
estiver na `main` da central-ativacao é o que aplica o digest em Homologação e
Produção, para as três Centrais, qualquer que seja a versão da Central no ar.

Este teste fixa esse contrato sem rede nem credenciais. Quando a central-ativacao
está clonada ao lado, também confere que os arquivos e as opções que o workflow
usa existem no executor.
"""
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parent.parent
workflow = yaml.safe_load((ROOT / '.github/workflows/promote-environment.yml').read_text())
steps = workflow['jobs']['promote']['steps']
names = [step.get('name', step.get('uses', '')) for step in steps]


def step(name):
    matches = [item for item in steps if item.get('name') == name]
    assert len(matches) == 1, f'passo ausente ou repetido: {name}'
    return matches[0]


# 1. Um único checkout, e é o do executor confiável: central-ativacao@main,
#    sem credenciais persistidas e sem submódulos. O App nunca é baixado.
checkouts = [item for item in steps if str(item.get('uses', '')).startswith('actions/checkout@')]
assert len(checkouts) == 1, 'a promoção não faz checkout do App, só do executor'
executor = step('Obter executor confiável')
assert executor['uses'] == 'actions/checkout@v5'
assert executor['with']['repository'] == 'oondemand/central-ativacao'
assert executor['with']['ref'] == 'main', 'o executor é sempre a main da central-ativacao'
assert executor['with']['path'] == 'executor'
assert executor['with']['persist-credentials'] is False
assert executor['with']['submodules'] is False

# 2. O token do Control Plane só alcança a central-ativacao.
token = step('Gerar token do Oon Control Plane')
assert token['with']['owner'] == 'oondemand'
assert token['with']['repositories'] == 'central-ativacao'

# 3. O digest é aplicado pelo deploy-central-dev.js do executor, com o digest do
#    contexto canônico (nada é reconstruído).
apply = step('Aplicar exatamente o mesmo digest')
assert apply['working-directory'] == 'executor'
command = ' '.join(apply['run'].split())
assert command.startswith('node scripts/actions/deploy-central-dev.js '), command
for option in ('--release "$RELEASE_ID"', '--api "$ACTIVATION_API_URL"', '--context "$RUNNER_TEMP/context.json"',
               '--image-digest "$IMAGE_DIGEST"'):
    assert option in command, option
assert not any('npm run build' in str(item.get('run', '')) or 'docker' in str(item.get('run', '')) for item in steps)

# 4. Ordem: endpoint validado antes do token do executor, executor antes do OIDC,
#    contexto antes do deploy.
order = [
    'Validar endpoint da Central',
    'Gerar token do Oon Control Plane',
    'Obter executor confiável',
    'Instalar runtime oficial',
    'Emitir identidade OIDC do executor',
    'Obter contexto canônico sem reconstruir',
    'Registrar promoção do digest existente',
    'Preparar identidade Kubernetes do publisher',
    'Aplicar exatamente o mesmo digest',
]
missing = [name for name in order if name not in names]
assert not missing, f'passos ausentes: {missing}'
positions = [names.index(name) for name in order]
assert positions == sorted(positions), 'ordem dos passos do executor mudou'

# 5. Arquivos do executor que o workflow usa.
used = sorted(set(re.findall(r'scripts/actions/[A-Za-z0-9_.-]+', (ROOT / '.github/workflows/promote-environment.yml').read_text())))
assert used == [
    'scripts/actions/deploy-central-dev.js',
    'scripts/actions/install-core.sh',
    'scripts/actions/prepare-publisher-kubeconfig.sh',
    'scripts/actions/publication-state.js',
], used

# 6. README documenta o executor e a ordem de merge.
readme = (ROOT / 'README.md').read_text()
assert '## Ordem de merge' in readme
assert '`oondemand/central-ativacao@main`' in readme

# 7. Com a central-ativacao ao lado, o executor tem o que o workflow chama.
central = ROOT.parent / 'central-ativacao'
if (central / 'scripts/actions').is_dir():
    for path in used:
        assert (central / path).is_file(), f'executor sem {path}'
    deploy = (central / 'scripts/actions/deploy-central-dev.js').read_text()
    for flag in ('--release', '--api', '--context', '--image-digest'):
        assert f'flag("{flag}"' in deploy, f'deploy-central-dev.js não lê {flag}'
    credential = central / 'backend/src/auth/deliveryCredential.js'
    if credential.is_file():
        text = credential.read_text()
        assert '"oondemand/oon-publish"' in text and '"promote-environment.yml"' in text
        assert re.search(r'PLATFORM_PROMOTION_REF \|\| "main"', text), 'a Central despacha a promoção na main'
    print('Executor contract ok (central-ativacao ao lado conferida)')
else:
    print('Executor contract ok (central-ativacao não está ao lado)')
