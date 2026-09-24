---
doc_id: eng-build-server-guide
title: Using the Build Server
doc_kind: standalone
version: null
effective_date: 2021-08-23
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Build and Release
---

# Using the Build Server

All product builds run on the Jenkins build server, `build01.corp.local`,
which sits in the server room on the 4th floor. This guide explains how to
set up a job for your project, trigger a build and pick up the result.

## Getting an account
Ask the Build and Release team for a Jenkins account through a HelpLine
ticket under *Access*. Your account uses your Windows username; you set a
separate Jenkins password the first time you log in at
`http://build01.corp.local:8080`.

## Setting up a job
1. Copy the *template-maven* job and name the copy after your repository.
2. Under *Source Code Management*, enter the SVN URL of your project's
   trunk, for example `svn://svn.corp.local/repos/payments/trunk`.
3. Under *Build Triggers*, tick *Poll SCM* and keep the default schedule.
   Jenkins checks SVN for new commits and starts a build when it finds one.
4. Under *Post-build Actions*, add *Archive the artifacts* with
   `target/*.war`.
5. Click *Save*.

## Running a build
Builds start automatically after a commit is picked up. To run one by hand,
open the job and click *Build Now*. Build01 has two executors, so only two
builds run at once; others wait in the queue.

## Getting the build output
Each successful build archives a WAR file. Download it from the job's
*Last Successful Artifacts* link. For deployment, copy the WAR file to the
release share at `\\teamvault\public\releases\<project>` and email the QA
Lead with the build number.

## Nightly builds
Every project also runs a full clean build every night. The results are
emailed to the project's mailing list each morning. Fix a broken nightly
build before starting new work.

## Problems
- **Build stuck in the queue:** another team's build is using both
  executors. Wait, or ask in the Build and Release channel.
- **Disk full on build01:** raise a HelpLine ticket. Do not delete other
  teams' workspaces.
