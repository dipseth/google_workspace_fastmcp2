# EmailSpec

**Symbol:** `ε`

## Description

Top-level email specification — analogous to Card in gchat.

Contains an ordered list of EmailBlocks that are rendered to MJML,
then compiled to responsive HTML via mjml_to_html().

## Valid Children

- EmailTheme

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `subject` | str | Yes | — |  |
| `preheader` | str? | No | — |  |
| `blocks` | list[Union[Union[HeroBlock[HeroBlock], TextBlock[TextBlock], ButtonBlock[ButtonBlock], ImageBlock[ImageBlock], ColumnsBlock[ColumnsBlock], SpacerBlock[SpacerBlock], DividerBlock[DividerBlock], FooterBlock[FooterBlock], HeaderBlock[HeaderBlock], SocialBlock[SocialBlock], TableBlock[TableBlock], AccordionBlock[AccordionBlock], CarouselBlock[CarouselBlock]]]] | Yes | — |  |
| `theme` | EmailTheme | No | — |  |
