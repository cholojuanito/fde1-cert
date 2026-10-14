# The ecosystem you deploy into

Where your application would actually run, inside your actual firm.

> **Week 1 starts this file. Week 9 finishes it.**
> TC1 Step 10 asks eight questions. The full Week 9 checklist has around thirty,
> and the eight are a strict subset — so nothing here gets thrown away.

Describe patterns, not specifics. "On-prem OpenShift, images from an internal
registry, no public egress" is useful to everyone and identifies nobody. Never
put real hostnames, IPs, or architecture diagrams in this file.

---

## Week 1 — the first eight questions

<!-- Answered in TC1 Step 10. Bring these back from a real conversation. -->

**Who did you ask?** (role, not name)

Infra and secops engineers

| # | Question | Answer |
| :---: | --- | --- |
| 1 | Where do internal apps run? (k8s, ECS, App Service, a VM someone maintains) | Both ECS and k8s |
| 2 | Which cloud? AWS, Azure, GCP, on-prem, several? | AWS and on prem |
| 3 | Is there an internal container registry? | Yes |
| 4 | How do users log in? (Okta, Entra ID, Ping, SAML, homegrown) | Okta and internal SAML |
| 5 | Can the app reach the internet? Egress proxy? Allowlist? | Yes through whitelists |
| 6 | Where do secrets come from? (Vault, Secrets Manager, Key Vault) | SSM in AWS |
| 7 | Who approves a deployment, and what review does it need? | Myself and other MLEs with permissions |
| 8 | Is there an approved internal LLM endpoint already? | internal, no. Github copilot API or Bedrock are our primary options |

**What surprised you?**

Not much, I've deployed in all environments before

**What would you have to change about your app to deploy there?**

Where it pulls secrets from during deployment and creates the environment variables.

---

## Week 1 — what your machine told you

### Local container runtime

- Runtime used: Docker Engine
- Machine restriction or workaround: None for my local machine

<!--
  Paste the egress probe output from Session 1 here. It is evidence, and it
  frequently disagrees with what people believe about their own network.
-->
### Network Probe

| Host | Why | Status | Signed by |
| --- | --- | --- | --- |
| pypi.org | Python packages | OK | GlobalSign nv-sa |
| files.pythonhosted.org | The actual wheel downloads | OK | GlobalSign nv-sa |
| api.openai.com | The model API | OK | Google Trust Services |
| cdn.jsdelivr.net | The CDN the Week 1 frontend uses | OK | GlobalSign nv-sa |
| huggingface.co | Open weights, Weeks 2 and 8 | OK | Amazon |
| registry-1.docker.io | Container images | OK | Amazon |
| github.com | This repository | OK | Sectigo Limited |

**Does this match what you were told in the table above?** Where it doesn't, that
gap is worth chasing — it usually means a proxy nobody documented.

---

## Week 9 — the full checklist

<!--
  TC9 extends this same file. Do not start a new one: the point is that the git
  history shows one continuous piece of work from Week 1 to Week 9.
-->

<!-- Week 9 -->
