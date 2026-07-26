# Result page assembly

A result page has a fixed number of page slots numbered from the top of the page
downwards in the order a reader encounters them. Slot one is the first thing a reader
sees; the highest-numbered slot sits at the bottom of the page.

The retrieval stack does not place documents on the page. It emits an ordered list of
organic results and hands that list to the renderer, which drops the results into the
page slots its template reserves for organic content. The remaining slots of that
template are occupied by non-organic surfaces such as merchandising cards, media stacks
and query refinement modules, none of which appear in the interaction logs.

Three templates were in rotation over the collection period.

| Template | Organic results | Notes |
|---|---|---|
| `list_v4` | 10 | One vertical column of organic results. |
| `grid_two_col` | 10 | Two columns of five. The stack's list fills the left column top to bottom, then the right column top to bottom, while a reader crosses the page row by row. |
| `feature_stack` | 7 | A media stack occupies the upper part of the page and organic results follow beneath it. |

`data/serp_templates.json` records the mapping for each template. `organic_slots` lists
the page slot each organic result lands in, in retrieval-stack order: the first entry is
the page slot given to the result the stack ranked first, the second entry is the slot
given to the result it ranked second, and so on. `reserved_slots` lists the page slots
that template holds back for non-organic surfaces.

The template used for a page is recorded per query in `data/queries.csv`. Templates were
assigned per query throughout the collection period and are not tied to a collection day.
