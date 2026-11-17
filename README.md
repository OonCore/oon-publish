# Oon Publish

Ponte pública e sem credenciais privilegiadas para solicitar a publicação de Centrais Oon.

Este repositório contém apenas workflows reutilizáveis. O código da plataforma, o executor de deploy e os segredos de infraestrutura permanecem em repositórios privados.

## Publicação em desenvolvimento

No repositório da Central:

```yaml
name: publish-dev

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  request:
    permissions:
      contents: read
      id-token: write
    uses: oondemand/oon-publish/.github/workflows/request-dev.yml@main
```

O workflow:

1. lê o `appCode` e as capabilities físicas requeridas do `oon.deploy.json`; capabilities funcionais são lidas do `central.app.json`;
2. solicita um token OIDC do GitHub vinculado ao repositório, branch, commit e workflow chamadores;
3. envia a solicitação para a Central de Ativações;
4. não recebe kubeconfig, token do registry, credencial do MongoDB ou chave do GitHub App.

Manifestos central.app.json v1 e v2 são aceitos durante a migração dos Apps existentes. O contrato v2 continua recomendado para novos Apps; a compatibilidade v1 evita interromper publicações enquanto cada App atualiza o Core e o manifesto.

A Central de Ativações valida a identidade OIDC, o App, o repositório, a branch e o commit antes de despachar o executor privado. Apps tenant-scoped também passam pelos gates de licença/entitlement. Os Apps comuns Meus Apps, Oon Workspace e Oon Docs usam o lifecycle tenantless sem licença artificial e declaram o mesmo contrato `none/common/authenticated_users/rbac/singleton`. Restrições internas, como a visibilidade de documentos, pertencem ao RBAC do próprio App.

### Branches de desenvolvimento

O `push` automático permanece restrito à branch padrão, normalmente `main`. Para validar código antes do merge, abra **Actions → publish-dev → Run workflow**, selecione a feature branch e confirme a execução. A branch e o SHA são obtidos dos claims OIDC emitidos pelo GitHub; parâmetros enviados pelo App não escolhem a fonte.

A publicação manual substitui o código do mesmo ambiente Dev do App. Ela não cria Preview, URL, namespace ou banco isolado por branch. A Central serializa as execuções para impedir duas publicações concorrentes no mesmo Dev.

Uma release originada de feature branch é exclusiva de Desenvolvimento e não pode ser promovida. A promoção somente é liberada depois que o mesmo SHA for atestado pela branch padrão ou que a publicação automática da branch padrão produzir o SHA resultante do merge.

## Endpoint canônico e cutover de infraestrutura

A publicação Dev resolve a Central de Ativações nesta ordem:

1. input explícito `activation_api_url` do workflow reutilizável;
2. variável organizacional `OON_ACTIVATION_API_URL`;
3. endpoint SaaS padrão `https://central-ativacao.oonapps.online/api`.

Usuários e organizações que publicam no SaaS não precisam criar variáveis. Não existe fallback para a infraestrutura anterior.

O endpoint deve usar HTTPS, terminar em `/api` e apontar exatamente para o hostname greenfield:

```text
OON_ACTIVATION_API_URL=https://central-ativacao.oonapps.online/api
```

Credenciais na URL, query string, fragmento, porta alternativa e qualquer domínio legado são recusados. Inputs e variáveis organizacionais aceitam só as três Centrais; outros hostnames são recusados:

| Central | Endpoint |
| --- | --- |
| Produção (padrão SaaS) | `https://central-ativacao.oonapps.online/api` |
| Homologação | `https://central-ativacao-hml.oonapps.online/api` |
| Desenvolvimento | `https://central-ativacao-dev.oonapps.online/api` |

Desde o marco 0.3.0, cada Central é um **ecossistema isolado**: banco próprio, segredos próprios e os próprios Apps em Dev, Homologação e Produção. Detalhes no ADR 0010 do oon-k8s-infra e em `docs/central-environments.md` da central-ativacao.

- A Central que criou o App é a dona dele. O scaffold do Oon Workspace grava a URL dela em `activation_api_url`, e o `publish-dev` do App sempre fala com essa Central.
- Nenhuma Central importa releases de outra.
- Os Apps da central-dev e da central-hml são publicados com os qualificadores `-cdev` e `-chml` no namespace e no host. Por isso, um `appCode` terminado em `-cdev` ou `-chml` é recusado já no `request-dev.yml`, antes de emitir o token OIDC. A Central também recusa, com `APP_CODE_RESERVED_SUFFIX`.

## Capabilities obrigatórias

```json
{
  "capabilities": {
    "pdfRendering": { "required": true, "minVersion": "1.0.0" }
  }
}
```

O workflow envia somente nomes e versões mínimas. A Central de Ativações
bloqueia a publicação antes do deploy quando o ambiente não possui uma
`PlatformCapabilityRegistration` compatível e devolve uma mensagem para
executar a reconciliação. Endpoint e credenciais da implementação técnica nunca
entram no build, no repositório chamador ou nos logs deste workflow.

`core.transactional-email` é uma capability funcional, local ao App. Ela deve ser declarada em `central.app.json`, com sua política de escopo e templates em `capabilitySettings`, e nunca em `oon.deploy.json`. O workflow valida essa declaração antes de solicitar a publicação; chaves do provedor são configuradas somente na tela operacional do próprio App.

## Versionamento

Enquanto a primeira etapa está em homologação, os consumidores usam `@main`. Após estabilização, o workflow deve ser consumido por uma tag imutável, como `@v1` ou por SHA completo.

## Promoção entre ambientes

`promote-environment.yml` é acionado exclusivamente pela Central de Ativações.
Ele recebe um `release_id`, obtém por OIDC o contexto canônico e aplica em
Homologação ou Produção o `imageDigest` já validado em Dev. O workflow não faz
checkout do App, não executa build e não publica uma nova imagem.

Antes de emitir o token OIDC, o workflow valida `activation_api_url` com as mesmas
regras do `request-dev.yml`: HTTPS, porta padrão, caminho `/api`, sem credenciais,
query ou fragmento, e somente os hosts `central-ativacao.oonapps.online`,
`central-ativacao-hml.oonapps.online` e `central-ativacao-dev.oonapps.online`.
Cada Central promove os Apps do próprio ecossistema. Qualquer outro endereço
encerra a execução sem token, sem kubeconfig e sem callback.

O Control Plane recusa artefatos anteriores ao contrato neutro de ambiente,
operações concorrentes, ausência de RBAC/entitlement/licença e Produção sem o
aceite de Homologação quando exigido. Falhas preservam o histórico e podem ser
reconciliadas de forma idempotente pelo Meus Apps.

### Executor da promoção

Este repositório não tem executor de deploy próprio. O `promote-environment.yml`:

1. gera um token do Oon Control Plane que só alcança a `central-ativacao`;
2. faz checkout de `oondemand/central-ativacao@main` em `executor/`, sem
   credenciais persistidas;
3. instala o runtime oficial com `scripts/actions/install-core.sh` e roda
   `scripts/actions/publication-state.js` e
   `scripts/actions/deploy-central-dev.js` de lá.

A Central despacha a promoção em `oon-publish@main`
(`PLATFORM_PROMOTION_REF`, padrão `main`), e a publicação Dev em
`central-ativacao/publish-central-dev.yml@main` (`PLATFORM_DELIVERY_REF`), que
roda o mesmo `deploy-central-dev.js`. Ou seja, quem aplica o digest em Dev, HML
e Prod, para as três Centrais, é sempre o executor que está na `main` da
central-ativacao no momento da execução, e não a versão da Central que está no
ar. Por isso o executor da `main` precisa continuar compatível com as Centrais
que ainda não foram atualizadas: no marco 0.3.0 ele deduz o ecossistema do
namespace e do host da Central, sem campo novo no contexto.
`test/executor-contract.py` fixa esse contrato e, com a central-ativacao
clonada ao lado, confere que os arquivos e as opções usados existem.

## Ordem de merge

Ordem do marco 0.3.0 (um ecossistema por Central). Cada passo é um merge
humano; nenhum deles dispara publicação, exceto onde indicado.

1. **`oon-platform`**, com o OonCore 0.8.0 publicado no npm. O
   `install-core.sh` do executor instala o Core do lock da central-ativacao, que
   só resolve depois da publicação.
2. **`oon-publish`** (este repositório). Só amplia a lista de Centrais aceitas
   (inclui `central-ativacao-hml`) e recusa códigos `-cdev`/`-chml`. Com a
   central-ativacao antiga na `main`, o executor continua recusando os
   namespaces qualificados, então nada passa a ser publicado fora do
   ecossistema de produção. Precisa vir antes da central-ativacao: depois
   dela, a central-hml passa a `primary` e despacha promoções com o próprio
   host, que a `main` antiga deste repositório recusaria.
3. **`oon-k8s-infra`**. Os workers da produção não mudam. Os workers
   `-cdev`/`-chml` só são instalados depois, pelo `configure-platform-integrations`.
4. **`central-ativacao`**, com o `deploy-central-dev.js` que aceita os
   namespaces `-cdev`/`-chml` e grava `oon.runtime/ecosystem`. A partir daqui, o
   executor da promoção e o da publicação Dev são os novos. Com
   `CENTRAL_DEV_AUTO_DEPLOY=true`, este merge já publica a central-dev.
5. Só então os Apps publicam com `central=desenvolvimento` ou
   `central=homologacao`.

Os Apps consomem `request-dev.yml@main`, e a Central só aceita a identidade
OIDC desse workflow em `refs/heads/main`. Uma branch deste repositório nunca é
usada por Apps nem pela Central: as mudanças só valem depois do merge.


## Apps singleton tenantless e credenciais de Deployment

Para um App global, o contexto de delivery usa `lifecycleMode=global_singleton` e uma identidade operacional composta por `deploymentId` e `deploymentToken`. O token é mascarado imediatamente pelo workflow, permanece somente no arquivo temporário protegido e é removido no cleanup. Ele nunca é enviado em URL, output ou resumo.

O deploy global não executa activation code de cliente. O mesmo Deployment é reconciliado por App + ambiente em retries, promoções e rollbacks; o digest da promoção continua sendo o artefato imutável produzido em Dev. Apps tenant-scoped preservam o contrato `tenant_activation`.

## A1/T1 — runtime common/shared

O modo canônico `platform_shared` usa a mesma identidade técnica de deployment
do caminho global, com configuração `multi_tenant/common/tenant_members/rbac/shared`.
A Central #447 fornece contexto/credencial por App e ambiente; o SDK #213 mantém
o tenant de dados por requisição e valida os bindings e a autoridade na Central.
O Publisher não inventa tenant técnico, AppLicense, slot ou código de ativação de
cliente. Promoção e rollback continuam usando o digest imutável e o aceite HML.

Este complemento somente amplia a seleção do protocolo de bootstrap no workflow
existente. Triggers, OIDC, mascaramento de segredos e gates não mudam. Os contratos
locais são executados; o workflow não foi disparado. `hybrid` e `licensed/shared`
não são autorizados por esse modo. A publicação do SDK e o rollout permanecem
etapas posteriores, fora deste PR.

## Segredos V1

`core.secrets` é opt-in em `central.app.json`, com `capabilitySettings["core.secrets"]={"enabled":true}` e arquitetura single_tenant/dedicated ou multi_tenant/shared (apps globais compartilhados, como o Financeiro Oon e o Ajuda Oon). O request repassa apenas essa declaração, nunca chave/credenciais. Depende da Central com suporte e executor com SDK 0.7.6 ou superior contendo a V1. A promoção mantém a declaração, provisionando chave independente no ambiente destino.

## Arquitetura #290

Novos manifestos omitem `deploymentMode`. O publisher transporta `availability` e `tenancyModel` para a Central, que aplica a regra canônica do SDK e deriva o contexto técnico. Um campo legado explícito é transportado para validação; contradição e `hybrid` são recusados pela Central antes de autorizar recursos. A validação local de `core.secrets` aceita a omissão para `single_tenant` e `multi_tenant`. Este workflow não decide licenciamento, capacidade ou acesso de clientes. Teste do transporte: `python3 test/secrets-contract.py`, inteiramente local, sem dispatch.
