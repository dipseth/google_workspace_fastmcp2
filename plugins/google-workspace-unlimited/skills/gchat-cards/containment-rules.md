# Containment Rules for card_framework

This document describes which components can contain which.

## Parent → Children Relationships

| Parent | Symbol | Children |
|--------|--------|----------|
| AccessoryWidget | `A_1` | `Ƀ`=ButtonList |
| Action | `ă` | `A_2`=ActionParameter, `♣`=Interaction, `λ`=LoadIndicator |
| ActionResponse | `▪` | `ð`=DialogAction, `ř`=ResponseType, `ų`=UpdatedWidget |
| ActionStatus | `♦` | `†`=Code |
| Annotation | `ą` | `A_0`=AnnotationType, `S_5`=SlashCommandMetadata, `ʉ`=UserMentionMetadata |
| Attachment | `Å` | `A_3`=AttachmentDataRef, `■`=DriveDataRef, `ş`=Source |
| BorderStyle | `β` | `ℬ`=BorderType, `‡`=Color |
| Button | `ᵬ` | `‡`=Color, `ɨ`=Icon, `ø`=OnClick, `ŧ`=Type |
| ButtonList | `Ƀ` | `ᵬ`=Button |
| Card | `©` | `◆`=CardAction, `C_1`=CardFixedFooter, `◇`=CardHeader, `●`=DisplayStyle, `○`=DividerStyle, +1 more |
| CardAction | `◆` | `ø`=OnClick |
| CardFixedFooter | `C_1` | `ᵬ`=Button |
| CardHeader | `◇` | `ι`=ImageType |
| CardWithId | `•` | `◆`=CardAction, `C_1`=CardFixedFooter, `◇`=CardHeader, `●`=DisplayStyle, `○`=DividerStyle, +1 more |
| Carousel | `◦` | `▼`=CarouselCard |
| CarouselCard | `▼` | `ŋ`=NestedWidget |
| ChatClientDataSourceMarkup | `C_4` | `S_4`=SpaceDataSource |
| Chip | `ℂ` | `ɨ`=Icon, `ø`=OnClick |
| ChipList | `ȼ` | `ℂ`=Chip, `ŀ`=Layout |
| CollapseControl | `C_0` | `ᵬ`=Button, `Ħ`=HorizontalAlignment |
| Column | `ç` | `Ħ`=HorizontalAlignment, `ħ`=HorizontalSizeStyle, `ν`=VerticalAlignment, `ʍ`=Widget |
| Columns | `¢` | `ç`=Column |
| CustomEmoji | `★` | `C_3`=CustomEmojiPayload |
| DateTimePicker | `◙` | `ă`=Action, `ŧ`=Type |
| DecoratedText | `δ` | `ᵬ`=Button, `ɨ`=Icon, `ø`=OnClick, `◄`=SwitchControl |
| DeletionMetadata | `D_0` | `ɖ`=DeletionType |
| Dialog | `đ` | `©`=Card |
| DialogAction | `ð` | `♦`=ActionStatus, `đ`=Dialog |
| Emoji | `ε` | `★`=CustomEmoji |
| EmojiReactionSummary | `ė` | `ε`=Emoji |
| Grid | `ℊ` | `β`=BorderStyle, `ǵ`=GridItem, `ø`=OnClick |
| GridItem | `ǵ` | `γ`=GridItemLayout, `Ħ`=HorizontalAlignment, `▫`=ImageComponent |
| HostAppDataSourceMarkup | `ℏ` | `C_4`=ChatClientDataSourceMarkup |
| Icon | `ɨ` | `ι`=ImageType, `ĸ`=KnownIcon, `ɯ`=MaterialIcon |
| Image | `ǐ` | `ø`=OnClick |
| ImageComponent | `▫` | `β`=BorderStyle, `I_0`=ImageCropStyle |
| ImageCropStyle | `I_0` | `◘`=ImageCropType |
| MaterialIcon | `ɯ` | (leaf) |
| Message | `μ` | `A_1`=AccessoryWidget, `▪`=ActionResponse, `ą`=Annotation, `☆`=AttachedGif, `Å`=Attachment, +10 more |
| NestedWidget | `ŋ` | `Ƀ`=ButtonList, `ǐ`=Image, `ʈ`=TextParagraph |
| OnClick | `ø` | `ă`=Action, `ɵ`=OpenLink, `►`=OverflowMenu |
| OverflowMenu | `►` | `O_0`=OverflowMenuItem |
| OverflowMenuItem | `O_0` | `ɨ`=Icon, `ʍ`=Widget |
| PlatformDataSource | `¶` | `C_2`=CommonDataSource, `ℏ`=HostAppDataSourceMarkup |
| Section | `§` | `C_0`=CollapseControl, `ʍ`=Widget |
| SelectionInput | `▲` | `ă`=Action, `¶`=PlatformDataSource, `S_0`=SelectionItem, `S_1`=SelectionType |
| SelectionItems | `S_2` | `S_0`=SelectionItem |
| SlashCommandMetadata | `S_5` | `S_6`=SlashCommandMetadataType, `ʊ`=User |
| Space | `ʂ` | `♥`=SpaceDetail, `ș`=SpaceType |
| Suggestions | `σ` | `S_3`=SuggestionItem |
| SwitchControl | `◄` | `ă`=Action, `♠`=ControlType |
| TextInput | `τ` | `ă`=Action, `σ`=Suggestions, `ŧ`=Type, `ʋ`=Validation |
| Thread | `Ʈ` | (leaf) |
| UpdatedWidget | `ų` | `S_2`=SelectionItems |
| User | `ʊ` | `υ`=UserType |
| UserMentionMetadata | `ʉ` | `ʊ`=User, `U_0`=UserMentionMetadataType |
| Validation | `ʋ` | `ɪ`=InputType |