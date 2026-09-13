"""Root application commands implemented as a discord.py Cog."""

from discord import app_commands
from discord.ext import commands


class HermesCommandsCog(commands.Cog):
    """Stable, hand-written Hermes slash commands."""

    def __init__(self, adapter) -> None:
        self.adapter = adapter

    async def _run(self, interaction, command: str) -> None:
        await self.adapter._run_simple_slash(interaction, command)

    @app_commands.command(description="Approve a pending dangerous command")
    async def approve(self, interaction, scope: str = ""): await self._run(interaction, f"/approve {scope}".strip())
    @app_commands.command(description="Run a command in the background")
    async def bg(self, interaction, command: str = ""): await self._run(interaction, f"/bg {command}".strip())
    @app_commands.command(description="Ask a quick follow-up question")
    async def btw(self, interaction, question: str = ""): await self._run(interaction, f"/btw {question}".strip())
    @app_commands.command(description="Compress the current conversation")
    async def compress(self, interaction): await self._run(interaction, "/compress")
    @app_commands.command(description="Deny a pending dangerous command")
    async def deny(self, interaction): await self._run(interaction, "/deny")
    @app_commands.command(description="Show available commands")
    async def help(self, interaction): await self._run(interaction, "/help")
    @app_commands.command(description="Show session insights")
    async def insights(self, interaction): await self._run(interaction, "/insights")
    @app_commands.command(description="Show or change the model")
    async def model(self, interaction, name: str = ""): await self._run(interaction, f"/model {name}".strip())
    @app_commands.command(description="Start a new conversation")
    async def new(self, interaction): await self._run(interaction, "/new")
    @app_commands.command(description="Set the assistant personality")
    async def personality(self, interaction, name: str = ""): await self._run(interaction, f"/personality {name}".strip())
    @app_commands.command(description="Create a plan")
    async def plan(self, interaction, request: str = ""): await self._run(interaction, f"/plan {request}".strip())
    @app_commands.command(description="Show queued work")
    async def queue(self, interaction): await self._run(interaction, "/queue")
    @app_commands.command(description="Set reasoning effort")
    async def reasoning(self, interaction, level: str = ""): await self._run(interaction, f"/reasoning {level}".strip())
    @app_commands.command(name="reload-mcp", description="Reload MCP servers")
    async def reload_mcp(self, interaction): await self._run(interaction, "/reload-mcp")
    @app_commands.command(name="reload-skills", description="Reload skills")
    async def reload_skills(self, interaction): await self._run(interaction, "/reload-skills")
    @app_commands.command(description="Reset the conversation")
    async def reset(self, interaction): await self._run(interaction, "/reset")
    @app_commands.command(description="Restart Hermes")
    async def restart(self, interaction): await self._run(interaction, "/restart")
    @app_commands.command(description="Resume the previous turn")
    async def resume(self, interaction): await self._run(interaction, "/resume")
    @app_commands.command(description="Retry the previous turn")
    async def retry(self, interaction): await self._run(interaction, "/retry")
    @app_commands.command(description="Set the home channel")
    async def sethome(self, interaction): await self._run(interaction, "/sethome")
    @app_commands.command(description="Show Hermes status")
    async def status(self, interaction): await self._run(interaction, "/status")
    @app_commands.command(description="Steer the active turn")
    async def steer(self, interaction, message: str = ""): await self._run(interaction, f"/steer {message}".strip())
    @app_commands.command(description="Stop the active turn")
    async def stop(self, interaction): await self._run(interaction, "/stop")
    @app_commands.command(description="Set the conversation title")
    async def title(self, interaction, title: str = ""): await self._run(interaction, f"/title {title}".strip())
    @app_commands.command(description="Undo the previous action")
    async def undo(self, interaction): await self._run(interaction, "/undo")
    @app_commands.command(description="Update Hermes")
    async def update(self, interaction): await self._run(interaction, "/update")
    @app_commands.command(description="Show usage")
    async def usage(self, interaction): await self._run(interaction, "/usage")
    @app_commands.command(description="Manage voice mode")
    async def voice(self, interaction, action: str = ""): await self._run(interaction, f"/voice {action}".strip())
