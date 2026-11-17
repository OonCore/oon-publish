"""Executor da promoção por ecossistema (marco 0.3.0, I-2), visto do oon-publish.

O promote-environment.yml roda `deploy-central-dev.js` de
`central-ativacao@main` para as três Centrais. Este teste carrega esse executor
(da central-ativacao clonada ao lado) do mesmo jeito que o workflow:
`normalizeContext(contexto, --api)` com o endpoint já validado pelo passo
"Validar endpoint da Central", e confere:

- namespaces `-cdev`/`-chml` aceitos para a Central do próprio ecossistema, nos
  três ambientes, com `oon.runtime/ecosystem` gravado nos rótulos de posse;
- compatibilidade com a Central de Produção anterior ao marco (contexto sem
  `ecosystem`): os namespaces de sempre continuam aceitos, com o rótulo
  `producao`;
- recusa de namespace de outro ecossistema, pelo host da Central ou pelo
  `ecosystem` declarado no contexto.

Sem rede e sem credenciais. Pulado quando a central-ativacao ao lado não tem o
executor do marco (ou as dependências do backend não estão instaladas).
"""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
CENTRAL = Path(os.environ.get('CENTRAL_ATIVACAO_DIR') or ROOT.parent / 'central-ativacao')
DEPLOY = CENTRAL / 'scripts/actions/deploy-central-dev.js'

PROBE = r"""
const deploy = require("./scripts/actions/deploy-central-dev.js");
const cases = JSON.parse(process.argv[1]);
const out = cases.map(({ context, api }) => {
  try {
    const ctx = deploy.normalizeContext(context, api);
    const ecosystem = deploy.assertRuntimeNamespace(ctx);
    const lifecycle = ctx.environment === "producao"
      ? deploy.productionRuntimeOwnership(ctx)
      : deploy.developmentRuntimeLifecycle(ctx, new Date());
    return { ok: true, ecosystem, label: lifecycle && lifecycle.labels["oon.runtime/ecosystem"] };
  } catch (error) {
    return { ok: false, error: String(error && error.message || error) };
  }
});
process.stdout.write(JSON.stringify(out));
"""

API = {
    'producao': 'https://central-ativacao.oonapps.online/api',
    'homologacao': 'https://central-ativacao-hml.oonapps.online/api',
    'desenvolvimento': 'https://central-ativacao-dev.oonapps.online/api',
}
QUALIFIER = {'producao': '', 'homologacao': '-chml', 'desenvolvimento': '-cdev'}
SUFFIX = {'desenvolvimento': '-dev', 'homologacao': '-hml', 'producao': '-prod'}


def context(environment, namespace, **extra):
    host = namespace.replace('oon-', '', 1) + '.oonapps.online'
    return {
        'appId': 'app-1', 'appCode': 'meus-apps', 'releaseId': 'rel-1', 'environment': environment,
        'namespace': namespace, 'frontendUrl': f'https://{host}', **extra,
    }


def skip(reason):
    print(f'Executor ecosystem contract pulado: {reason}')
    raise SystemExit(0)


if not DEPLOY.is_file():
    skip('central-ativacao não está ao lado')
if 'assertRuntimeNamespace' not in DEPLOY.read_text():
    skip('o executor ao lado ainda não tem o contrato por ecossistema (I-2)')

cases = []
expected = []
for central, api in API.items():
    for environment, suffix in SUFFIX.items():
        namespace = 'oon-meus-apps' + suffix + QUALIFIER[central]
        # Central do marco (declara o ecossistema) e Central anterior (não declara).
        cases.append({'context': context(environment, namespace, ecosystem=central), 'api': api})
        expected.append(('aceito', central))
        cases.append({'context': context(environment, namespace), 'api': api})
        expected.append(('aceito', central))
        # O mesmo namespace pedido por outra Central é recusado.
        for other, other_api in API.items():
            if other != central:
                cases.append({'context': context(environment, namespace), 'api': other_api})
                expected.append(('recusado', None))
                cases.append({'context': context(environment, namespace, ecosystem=other), 'api': api})
                expected.append(('recusado', None))
# Namespace fora do contrato de qualquer ecossistema.
for namespace, environment in [('oon-meus-apps-dev-cdev-x', 'desenvolvimento'), ('oon-meus-apps-prod-chml', 'homologacao'),
                               ('kube-system', 'producao'), ('oon-meus-apps-hml-cdev', 'desenvolvimento')]:
    cases.append({'context': context(environment, namespace), 'api': API['desenvolvimento']})
    expected.append(('recusado', None))

result = subprocess.run(['node', '-e', PROBE, json.dumps(cases)], cwd=CENTRAL, capture_output=True, text=True)
if result.returncode != 0:
    if "Cannot find module '@oondemand/oon-core-back'" in result.stderr:
        skip('dependências do backend da central-ativacao não instaladas')
    raise AssertionError(result.stderr)
outcomes = json.loads(result.stdout)
assert len(outcomes) == len(cases)
for case, (want, ecosystem), got in zip(cases, expected, outcomes):
    label = f"{case['api']} {case['context']['namespace']} ecosystem={case['context'].get('ecosystem')}"
    if want == 'aceito':
        assert got['ok'], (label, got)
        assert got['ecosystem'] == ecosystem, (label, got)
        assert got['label'] == ecosystem, (label, 'rótulo oon.runtime/ecosystem', got)
    else:
        assert not got['ok'], (label, got)
print(f'{len(cases)} executor ecosystem cases passed (central-ativacao ao lado)')
