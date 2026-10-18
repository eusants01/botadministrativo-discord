from __future__ import annotations

from collections import deque
from functools import wraps
import re
from typing import Any
from uuid import uuid4
from weakref import WeakValueDictionary

import discord


_ACTION_SELECT_ID = 'sants:v2:actions'
_INSTALLED = False
_DYNAMIC_ITEM_CLASSES: list[type] = []
_ACTION_REGISTRY: WeakValueDictionary[str, Any] = WeakValueDictionary()
_HANDLED_INTERACTIONS: set[int] = set()
_HANDLED_ORDER: deque[int] = deque()


def _registered_action(
    interaction: discord.Interaction, action_id: str
) -> tuple[bool, Any]:
    try:
        message = interaction.message
        component_type = interaction.data['component_type']
        store = interaction.client._connection._view_store
        custom_id = interaction.data['custom_id']
        for message_id in (message.id, None):
            item = store._views.get((component_type, message_id), {}).get(custom_id)
            actions = getattr(item, 'actions', None)
            if actions is not None and action_id in actions:
                return True, actions[action_id]
    except (AttributeError, KeyError, TypeError):
        pass
    return False, _ACTION_REGISTRY.get(action_id)


async def _dispatch_action(interaction: discord.Interaction, action: Any) -> None:
    interaction_id = interaction.id
    if interaction_id in _HANDLED_INTERACTIONS:
        return
    if len(_HANDLED_ORDER) == 4096:
        _HANDLED_INTERACTIONS.discard(_HANDLED_ORDER.popleft())
    _HANDLED_ORDER.append(interaction_id)
    _HANDLED_INTERACTIONS.add(interaction_id)

    button = _component(action)
    if button.disabled:
        await interaction.response.send_message(
            'Essa ação não está disponível no momento.', ephemeral=True
        )
        return
    if button.url:
        await interaction.response.send_message(button.url, ephemeral=True)
        return

    previous_data = interaction.data
    interaction.data = dict(previous_data or {})
    interaction.data.update(
        custom_id=button.custom_id,
        component_type=discord.ComponentType.button.value,
    )
    try:
        await action.callback(interaction)
    finally:
        interaction.data = previous_data


def _component(item: Any) -> Any:
    return getattr(item, 'item', item)


def _is_button(item: Any) -> bool:
    return isinstance(_component(item), discord.ui.Button)


class _ActionSelect(discord.ui.Select):
    def __init__(self, actions: list[Any], row: int | None = None):
        self.actions: dict[str, Any] = {}
        options = []
        for index, action in enumerate(actions):
            button = _component(action)
            label = (button.label or f'Ação {index + 1}')[:100]
            value = button.custom_id or f'action:{uuid4().hex}'
            self.actions[value] = action
            _ACTION_REGISTRY[value] = action
            options.append(discord.SelectOption(
                label=label,
                value=value,
                emoji=button.emoji,
                description='Executa a ação correspondente'[:100],
            ))
        super().__init__(
            placeholder='Selecione uma ação',
            min_values=1,
            max_values=1,
            options=options,
            custom_id=_ACTION_SELECT_ID,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await _dispatch_action(interaction, self.actions[self.values[0]])


class _DynamicActionSelect(
    discord.ui.DynamicItem[discord.ui.Select],
    template=re.escape(_ACTION_SELECT_ID),
):
    def __init__(self, options: list[discord.SelectOption] | None = None):
        super().__init__(discord.ui.Select(
            custom_id=_ACTION_SELECT_ID,
            placeholder='Selecione uma ação',
            min_values=1,
            max_values=1,
            options=options or [discord.SelectOption(label='Ação', value='')],
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(item.options)

    async def callback(self, interaction: discord.Interaction) -> None:
        action_id = (interaction.data or {}).get('values', [None])[0]
        is_registered, action = _registered_action(interaction, action_id)
        if is_registered:
            return
        if action is not None:
            await _dispatch_action(interaction, action)
            return
        for item_class in _DYNAMIC_ITEM_CLASSES:
            template = getattr(
                item_class,
                '__discord_ui_compiled_template__',
                getattr(item_class, '__discord_ui_template__', None),
            )
            if isinstance(template, str):
                template = re.compile(template)
            match = template.fullmatch(action_id) if template and action_id else None
            if match is None:
                continue
            button = discord.ui.Button(custom_id=action_id)
            action = await item_class.from_custom_id(interaction, button, match)
            await _dispatch_action(interaction, action)
            return
        await interaction.response.send_message(
            'Essa ação não está mais disponível.', ephemeral=True
        )


class _ConvertedView(discord.ui.View):
    def __init__(self, source: discord.ui.View):
        super().__init__(timeout=source.timeout)
        self.source = source
        children = list(source.children)
        buttons = [child for child in children if _is_button(child)]
        other_items = [child for child in children if not _is_button(child)]
        if buttons:
            other_items.append(_ActionSelect(buttons))
        for item in other_items:
            item._view = None
            self.add_item(item)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.source.interaction_check(interaction)

    async def on_timeout(self) -> None:
        await self.source.on_timeout()

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        await self.source.on_error(interaction, error, item)


class _ConvertedLayoutView(discord.ui.LayoutView):
    def __init__(self, source: discord.ui.View | None):
        super().__init__(timeout=source.timeout if source is not None else None)
        self.source = source

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.source is None:
            return True
        return await self.source.interaction_check(interaction)

    async def on_timeout(self) -> None:
        if self.source is not None:
            await self.source.on_timeout()

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        if self.source is not None:
            await self.source.on_error(interaction, error, item)
        else:
            raise error


def _convert_view(view: discord.ui.View | None) -> discord.ui.View | None:
    if view is None or isinstance(view, (discord.ui.LayoutView, _ConvertedView)):
        return view
    if not any(_is_button(child) for child in view.children):
        return view
    return _ConvertedView(view)


def _embed_text(embed: discord.Embed) -> str:
    parts: list[str] = []
    if embed.author.name:
        author = f'**{embed.author.name}**'
        if embed.author.url:
            author = f'[{author}]({embed.author.url})'
        parts.append(author)
    if embed.title:
        title = f'# {embed.title}'
        if embed.url:
            title = f'[{title}]({embed.url})'
        parts.append(title)
    if embed.description:
        parts.append(embed.description)
    for field in embed.fields:
        parts.append(f'**{field.name}**\n{field.value}')
    if embed.footer.text:
        parts.append(f'-# {embed.footer.text}')
    if embed.timestamp:
        parts.append(f'-# {discord.utils.format_dt(embed.timestamp, style="R")}')
    return '\n\n'.join(parts)


def _split_text(text: str, limit: int = 4000) -> list[str]:
    chunks: list[str] = []
    while len(text) > limit:
        boundary = text.rfind('\n', 0, limit)
        if boundary < limit // 2:
            boundary = limit
        chunks.append(text[:boundary])
        text = text[boundary:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def _layout_view(
    embeds: list[discord.Embed],
    content: str | None,
    source_view: discord.ui.View | None,
) -> discord.ui.LayoutView:
    converted = _convert_view(source_view)
    layout = _ConvertedLayoutView(source_view)
    text_parts = [content] if content else []
    text_parts.extend(_embed_text(embed) for embed in embeds)
    text = '\n\n'.join(part for part in text_parts if part)
    items: list[Any] = [discord.ui.TextDisplay(chunk) for chunk in _split_text(text)]

    media_items: list[Any] = []
    for embed in embeds:
        media = []
        if embed.image and embed.image.url:
            media.append(discord.ui.MediaGalleryItem(
                media=embed.image.url, description='Imagem'
            ))
        if embed.thumbnail and embed.thumbnail.url:
            media.append(discord.ui.MediaGalleryItem(
                media=embed.thumbnail.url, description='Miniatura'
            ))
        if media:
            media_items.append(discord.ui.MediaGallery(*media))

    if media_items:
        if items:
            try:
                items.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            except Exception:
                pass
        items.extend(media_items)

    action_rows: list[Any] = []
    if converted is not None:
        for item in converted.children:
            item._view = None
            row = discord.ui.ActionRow()
            row.add_item(item)
            action_rows.append(row)

    if action_rows:
        if items:
            try:
                items.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            except Exception:
                pass
        items.extend(action_rows)

    accent = next((embed.color for embed in embeds if embed.color), None)
    for start in range(0, len(items), 10):
        batch = items[start:start + 10]
        container = discord.ui.Container(
            *batch,
            accent_colour=accent,
        )
        layout.add_item(container)
    return layout


def _message_kwargs(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    existing: discord.Message | None = None,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    result = dict(kwargs)
    missing = discord.utils.MISSING
    supplied_embed = result.get('embed', missing)
    supplied_embeds = result.get('embeds', missing)
    if supplied_embeds is not missing:
        embeds = list(supplied_embeds or [])
    elif supplied_embed is not missing:
        embeds = [supplied_embed] if supplied_embed is not None else []
    elif existing is not None:
        embeds = list(existing.embeds)
    else:
        embeds = []

    content = result.get('content', args[0] if args else missing)
    if content is missing:
        content = existing.content if existing is not None else None
    view = result.get('view')

    if embeds:
        result['view'] = _layout_view(embeds, content, view)
        result['content'] = None
        if supplied_embeds is not missing:
            result['embeds'] = []
            result.pop('embed', None)
        else:
            result['embed'] = None
            result.pop('embeds', None)
        if args:
            args = (None, *args[1:])
    elif view is not None:
        result['view'] = _convert_view(view)
    return args, result


def install_components_v2(bot: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    def patch(cls: type, method_name: str, existing_message: Any = None) -> None:
        original = getattr(cls, method_name)

        @wraps(original)
        async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            message = existing_message(self) if existing_message else None
            args, kwargs = _message_kwargs(args, kwargs, message)
            return await original(self, *args, **kwargs)

        setattr(cls, method_name, wrapped)

    patch(discord.abc.Messageable, 'send')
    patch(discord.InteractionResponse, 'send_message')
    patch(
        discord.InteractionResponse,
        'edit_message',
        lambda response: getattr(response._parent, 'message', None),
    )
    patch(discord.Webhook, 'send')
    patch(discord.Message, 'edit', lambda message: message)
    partial_message = getattr(discord, 'PartialMessage', None)
    if partial_message is not None and partial_message.edit is not discord.Message.edit:
        patch(partial_message, 'edit', lambda message: message)

    original_edit_response = discord.Interaction.edit_original_response

    @wraps(original_edit_response)
    async def edit_original_response(
        interaction: discord.Interaction, *args: Any, **kwargs: Any
    ) -> Any:
        existing = None
        if 'embed' not in kwargs and 'embeds' not in kwargs:
            try:
                existing = await interaction.original_response()
            except discord.HTTPException:
                pass
        args, kwargs = _message_kwargs(args, kwargs, existing)
        return await original_edit_response(interaction, *args, **kwargs)

    discord.Interaction.edit_original_response = edit_original_response

    original_add_view = bot.add_view

    def add_view(view: discord.ui.View, *args: Any, **kwargs: Any) -> Any:
        return original_add_view(_convert_view(view), *args, **kwargs)

    bot.add_view = add_view

    original_add_dynamic_items = bot.add_dynamic_items

    def add_dynamic_items(*item_classes: type) -> Any:
        for item_class in item_classes:
            if item_class not in _DYNAMIC_ITEM_CLASSES:
                _DYNAMIC_ITEM_CLASSES.append(item_class)
        registered = getattr(bot, '_sants_v2_dynamic_select_registered', False)
        if not registered:
            item_classes += (_DynamicActionSelect,)
            bot._sants_v2_dynamic_select_registered = True
        return original_add_dynamic_items(*item_classes)

    bot.add_dynamic_items = add_dynamic_items
    _INSTALLED = True

    