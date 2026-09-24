---
doc_id: eng-local-environment-setup
title: Local Development Environment Setup
doc_kind: standalone
version: null
effective_date: 2026-01-26
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Developer Experience
---

# Local Development Environment Setup

This guide takes you from a freshly issued company laptop to running a
service locally. Do the steps in order. You need repository access first; see
the guide on getting access to code repositories.

## 1. Install the base tools
Install these from the self-service software catalogue:

- Git
- Docker Desktop
- Visual Studio Code or IntelliJ IDEA
- The GitHub CLI

If a tool is not in the catalogue, raise a software request in the IT service
portal. The Software Installation Policy explains how requests are handled.

## 2. Install language toolchains
We use version managers so each repository can pin its own versions:

- **Python:** install `pyenv`, then run `pyenv install` inside the repository.
  It reads the `.python-version` file.
- **Node.js:** install `nvm`, then run `nvm use` inside the repository. It
  reads the `.nvmrc` file.
- **Java:** install SDKMAN and run `sdk env install`.

## 3. Configure Git
```
git config --global user.name "Your Name"
git config --global user.email "you@company.example"
git config --global pull.rebase true
```
Add an SSH key to your GitHub account, or run `gh auth login`.

## 4. Connect to internal services
Package mirrors and the container registry are only reachable from the office
network or over the VPN. Connect to the VPN before running your first build.
See the VPN Access Policy for how to connect.

## 5. Clone and run a service
```
gh repo clone company/<service>
cd <service>
make setup
make run
```
`make setup` installs dependencies and starts local databases in Docker.
`make run` starts the service on the port shown in its README.

## If something goes wrong
- **Docker will not start:** check that virtualisation is enabled, then ask
  in #dev-environment.
- **Dependency download fails:** check you are on the VPN, then run
  `make doctor`, which checks common settings.
- **Still stuck:** post the output of `make doctor` in #dev-environment.
