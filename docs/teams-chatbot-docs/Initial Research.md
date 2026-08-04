This was initial research into how the agent sdk worked when the user doesn't have the ability to create the correct stuff in the Entra tenant.

SUMMARY 2026/03/02 - was able to get local demos set up (without having to have a tenant) on a few of the agent sdk scaffolds, including Agents for Microsoft 365 Copilot -> Custom Engine Agent and Apps for Microsoft 365 / Teams Agents and Apps -> General Teams Agent.  These are in ~/dev/vscode-365-agents/... 

https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/debug-your-agents-playground?tabs=vscode%2Cclijs#limitations

looking like it wants me to get a dev env (using my cornell identity was a no-go)
![[SCR-20260302-rqtr.png]]


after I created the blank declarative agent, I got this, clicked on "use test tenant"
![[SCR-20260302-rryk-3.png]]


![[SCR-20260302-rsrt.png]]



# 2026-03-27
got my admin user in the dev tenant set up
had a [chat with copilot](https://m365.cloud.microsoft/chat/conversation/3f81ad25-8724-407a-beae-d49a160b0dfe) about what perms are needed to set up one of these things (looks like maybe it can work without ANY admin, if the bot itself doesn't need to hit any MS resources)
next up: create one of these things, get an unprivileged user set up so I can try setting one up and blessing it with my admin user, try implementing bot in n8n