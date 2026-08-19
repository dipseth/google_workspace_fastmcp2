# Structure DSL

Google Chat cards use a compact DSL notation for defining structure.

## Basic Syntax

```
§[δ×3, Ƀ[ᵬ×2]]
```

Means: Section with 3 DecoratedText items and a ButtonList with 2 Buttons.

## Notation Rules

- **Symbols**: Each component has a unique Unicode symbol (see `symbols.md`)
- **Brackets**: `[]` denote children of a container
- **Multiplier**: `×N` creates N copies of a component
- **Comma**: Separates sibling components

## Symbol Table

**A:** A_1=AccessoryWidget, ă=Action, A_2=ActionParameter, ■=ActionResponse, ♥=ActionStatus, ą=Annotation, A_0=AnnotationType, ★=AttachedGif, Å=Attachment, A_3=AttachmentDataRef, α=AutoNumber, ǎ=auto
**B:** β=BorderStyle, ℬ=BorderType, ᵬ=Button, Ƀ=ButtonList
**C:** ©=Card, ◦=CardAction, C_1=CardFixedFooter, ◆=CardHeader, •=CardWithId, C_5=Carousel, C_6=CarouselCard, C_4=ChatClientDataSourceMarkup, ℂ=Chip, ȼ=ChipList, †=Code, C_0=CollapseControl, ‡=Color, ç=Column, ¢=Columns, C_2=CommonDataSource, ☆=ControlType, ◇=CustomEmoji, C_3=CustomEmojiPayload
**D:** ▪=DateTimePicker, δ=DecoratedText, D_0=DeletionMetadata, ɖ=DeletionType, đ=Dialog, ð=DialogAction, ▲=DisplayStyle, Đ=Divider, ▼=DividerStyle, ●=DriveDataRef
**E:** ε=Emoji, ė=EmojiReactionSummary
**F:** ƒ=Field, ℱ=FrozenInstanceError
**G:** ǧ=GenericAlias, ℊ=Grid, ǵ=GridItem, γ=GridItemLayout
**H:** Ħ=HorizontalAlignment, ħ=HorizontalSizeStyle, ℏ=HostAppDataSourceMarkup
**I:** ɨ=Icon, ǐ=Image, □=ImageComponent, I_0=ImageCropStyle, ▫=ImageCropType, ι=ImageType, ı=InitVar, ɪ=InputType, ♠=Interaction
**K:** ĸ=KnownIcon
**L:** ŀ=Layout, ℓ=LetterCase, λ=LoadIndicator
**M:** ɱ=MatchedUrl, ɯ=MaterialIcon, μ=Message
**N:** ŋ=NestedWidget
**O:** ø=OnClick, ω=OnClose, Ω=OpenAs, ɵ=OpenLink, ♦=OverflowMenu, O_0=OverflowMenuItem
**P:** ¶=PlatformDataSource
**Q:** ʠ=QuotedMessageMetadata
**R:** ɽ=Renderable, ř=ResponseType
**S:** §=Section, ◄=SelectionInput, ◙=SelectionItem, S_0=SelectionItems, ◘=SelectionType, ○=SlashCommand, S_3=SlashCommandMetadata, S_4=SlashCommandMetadataType, ş=Source, ʂ=Space, S_2=SpaceDataSource, ♣=SpaceDetail, ș=SpaceType, S_1=SuggestionItem, σ=Suggestions, ►=SwitchControl
**T:** τ=TextInput, ʈ=TextParagraph, Ʈ=Thread, ŧ=Type, ƭ=TypeVar
**U:** ü=Union, ų=UpdatedWidget, ʊ=User, ʉ=UserMentionMetadata, U_0=UserMentionMetadataType, υ=UserType
**V:** ʋ=Validation, ν=VerticalAlignment
**W:** ʍ=Widget

## Examples

- `§[δ] - Simple section with one DecoratedText`
- `§[δ×3, Ƀ[ᵬ×2]] - Section with 3 texts and 2 buttons`
- `§[ℊ[ǵ×4]] - Section with a 4-item Grid`
- `§[δ, ǐ, Ƀ[ᵬ]] - Section with text, image, and button`


## Examples

- `§[δ] - Simple section with one DecoratedText`
- `§[δ×3, Ƀ[ᵬ×2]] - Section with 3 texts and 2 buttons`
- `§[ℊ[ǵ×4]] - Section with a 4-item Grid`
- `§[δ, ǐ, Ƀ[ᵬ]] - Section with text, image, and button`
