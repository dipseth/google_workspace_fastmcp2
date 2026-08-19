# Containment Rules for card_framework

This document describes which components can contain which.

## Parent → Children Relationships

| Parent | Symbol | Children |
|--------|--------|----------|
| AccessoryWidget | `A_1` | `Ƀ`=ButtonList |
| Action | `ă` | `A_2`=ActionParameter, `λ`=LoadIndicator, `♣`=Interaction, `A_2`=ActionParameter, `λ`=LoadIndicator, +247 more |
| ActionResponse | `▪` | `ř`=ResponseType, `ð`=DialogAction, `ų`=UpdatedWidget, `ř`=ResponseType, `ð`=DialogAction, +1 more |
| ActionStatus | `♦` | `†`=Code, `†`=Code, `†`=Code, `†`=Code |
| Annotation | `ą` | `A_0`=AnnotationType, `ʉ`=UserMentionMetadata, `S_5`=SlashCommandMetadata, `A_0`=AnnotationType, `ʉ`=UserMentionMetadata, +1 more |
| Attachment | `Å` | `ş`=Source, `A_3`=AttachmentDataRef, `■`=DriveDataRef, `ş`=Source, `A_3`=AttachmentDataRef, +1 more |
| BorderStyle | `β` | `ℬ`=BorderType, `‡`=Color, `ℬ`=BorderType, `‡`=Color, `ℬ`=BorderType, +5 more |
| Button | `ᵬ` | `ɨ`=Icon, `‡`=Color, `ø`=OnClick, `ŧ`=Type, `ɨ`=Icon, +143 more |
| ButtonList | `Ƀ` | `ᵬ`=Button, `ᵬ`=Button, `ᵬ`=Button |
| Card | `©` | `◇`=CardHeader, `§`=Section, `◆`=CardAction, `○`=DividerStyle, `C_1`=CardFixedFooter, +37 more |
| CardAction | `◆` | `ø`=OnClick, `ø`=OnClick, `ø`=OnClick, `ø`=OnClick, `ø`=OnClick, +4 more |
| CardFixedFooter | `C_1` | `ᵬ`=Button |
| CardHeader | `◇` | `ι`=ImageType, `ι`=ImageType, `ι`=ImageType, `ι`=ImageType, `ι`=ImageType, +12 more |
| CardWithId | `•` | `◇`=CardHeader, `§`=Section, `◆`=CardAction, `○`=DividerStyle, `C_1`=CardFixedFooter, +9 more |
| Carousel | `◦` | `▼`=CarouselCard |
| CarouselCard | `▼` | `ŋ`=NestedWidget |
| ChatClientDataSourceMarkup | `C_4` | `S_4`=SpaceDataSource, `S_4`=SpaceDataSource, `S_4`=SpaceDataSource, `S_4`=SpaceDataSource |
| Chip | `ℂ` | `ɨ`=Icon, `ø`=OnClick, `ɨ`=Icon, `ø`=OnClick |
| ChipList | `ȼ` | `ŀ`=Layout, `ℂ`=Chip |
| CollapseControl | `C_0` | `Ħ`=HorizontalAlignment, `ᵬ`=Button |
| Column | `ç` | `ħ`=HorizontalSizeStyle, `Ħ`=HorizontalAlignment, `ν`=VerticalAlignment, `ʍ`=Widget, `ħ`=HorizontalSizeStyle, +3 more |
| Columns | `¢` | `ç`=Column |
| CustomEmoji | `★` | `C_3`=CustomEmojiPayload, `C_3`=CustomEmojiPayload, `C_3`=CustomEmojiPayload, `C_3`=CustomEmojiPayload |
| DateTimePicker | `◙` | `ŧ`=Type, `ă`=Action |
| DecoratedText | `δ` | `ɨ`=Icon, `ɨ`=Icon, `ø`=OnClick, `ᵬ`=Button, `◄`=SwitchControl, +1 more |
| DeletionMetadata | `D_0` | `ɖ`=DeletionType, `ɖ`=DeletionType |
| Dialog | `đ` | `©`=Card, `©`=Card, `©`=Card, `©`=Card |
| DialogAction | `ð` | `♦`=ActionStatus, `đ`=Dialog, `♦`=ActionStatus, `đ`=Dialog, `♦`=ActionStatus, +1 more |
| Emoji | `ε` | `★`=CustomEmoji, `★`=CustomEmoji, `★`=CustomEmoji |
| EmojiReactionSummary | `ė` | `ε`=Emoji, `ε`=Emoji |
| Grid | `ℊ` | `ǵ`=GridItem, `β`=BorderStyle, `ø`=OnClick |
| GridItem | `ǵ` | `▫`=ImageComponent, `Ħ`=HorizontalAlignment, `γ`=GridItemLayout, `▫`=ImageComponent, `Ħ`=HorizontalAlignment, +1 more |
| HostAppDataSourceMarkup | `ℏ` | `C_4`=ChatClientDataSourceMarkup, `C_4`=ChatClientDataSourceMarkup, `C_4`=ChatClientDataSourceMarkup |
| Icon | `ɨ` | `ɯ`=MaterialIcon, `ĸ`=KnownIcon, `ι`=ImageType |
| Image | `ǐ` | `ø`=OnClick |
| ImageComponent | `▫` | `I_0`=ImageCropStyle, `β`=BorderStyle, `I_0`=ImageCropStyle, `β`=BorderStyle, `I_0`=ImageCropStyle, +1 more |
| ImageCropStyle | `I_0` | `◘`=ImageCropType, `◘`=ImageCropType, `◘`=ImageCropType, `◘`=ImageCropType |
| MaterialIcon | `ɯ` | (leaf) |
| Message | `μ` | `□`=SlashCommand, `ą`=Annotation, `•`=CardWithId, `D_0`=DeletionMetadata, `☆`=AttachedGif, +10 more |
| NestedWidget | `ŋ` | `Ƀ`=ButtonList, `ʈ`=TextParagraph, `ǐ`=Image |
| OnClick | `ø` | `ă`=Action, `ɵ`=OpenLink, `►`=OverflowMenu, `ă`=Action, `ă`=Action, +183 more |
| OverflowMenu | `►` | `O_0`=OverflowMenuItem, `O_0`=OverflowMenuItem, `O_0`=OverflowMenuItem, `O_0`=OverflowMenuItem, `O_0`=OverflowMenuItem, +34 more |
| OverflowMenuItem | `O_0` | `ɨ`=Icon, `ʍ`=Widget, `ɨ`=Icon, `ʍ`=Widget, `ɨ`=Icon, +51 more |
| PlatformDataSource | `¶` | `C_2`=CommonDataSource, `ℏ`=HostAppDataSourceMarkup, `C_2`=CommonDataSource, `ℏ`=HostAppDataSourceMarkup |
| Section | `§` | `ʍ`=Widget, `C_0`=CollapseControl, `ʍ`=Widget, `C_0`=CollapseControl, `ʍ`=Widget, +13 more |
| SelectionInput | `▲` | `¶`=PlatformDataSource, `S_1`=SelectionType, `S_0`=SelectionItem, `ă`=Action |
| SelectionItems | `S_2` | `S_0`=SelectionItem, `S_0`=SelectionItem, `S_0`=SelectionItem, `S_0`=SelectionItem |
| SlashCommandMetadata | `S_5` | `ʊ`=User, `S_6`=SlashCommandMetadataType, `ʊ`=User, `S_6`=SlashCommandMetadataType, `ʊ`=User, +1 more |
| Space | `ʂ` | `ș`=SpaceType, `♥`=SpaceDetail, `ș`=SpaceType, `♥`=SpaceDetail |
| Suggestions | `σ` | `S_3`=SuggestionItem, `S_3`=SuggestionItem |
| SwitchControl | `◄` | `ă`=Action, `♠`=ControlType, `ă`=Action, `♠`=ControlType |
| TextInput | `τ` | `ŧ`=Type, `ă`=Action, `σ`=Suggestions, `ă`=Action, `ʋ`=Validation |
| Thread | `Ʈ` | (leaf) |
| UpdatedWidget | `ų` | `S_2`=SelectionItems, `S_2`=SelectionItems, `S_2`=SelectionItems |
| User | `ʊ` | `υ`=UserType, `υ`=UserType, `υ`=UserType, `υ`=UserType, `υ`=UserType, +4 more |
| UserMentionMetadata | `ʉ` | `ʊ`=User, `U_0`=UserMentionMetadataType, `ʊ`=User, `U_0`=UserMentionMetadataType, `ʊ`=User, +1 more |
| Validation | `ʋ` | `ɪ`=InputType, `ɪ`=InputType |