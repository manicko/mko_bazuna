
? ??????? ? ? ?????? C:\py_dev/mko_bazuna\.ai/problems/Decision_020.md
C:\py_dev/mko_bazuna\.ai/problems/20_catalog-menu-breadcrumb-fix_spec.md
C:\py_dev/mko_bazuna\.ai/plans/done/20_catalog-menu-breadcrumb-fix_plan_DONE.md

?? ????????????? ??????? ???? ? breadcrumbs.
???? ????????, ?? ???????? ?? ??????.

1) Breadcrumbs ?? ???????????? ?? ????????? ?????, ???????? http://localhost:8000/category/business/ http://localhost:8000/

   Root Cause Analysis (completed):

   Commit `2a72514` addressed Spec_020 items, but three deeper root causes remain:

   RC-A: `get_children_count` does not exist on the Category model.
   `header_catalog.html` (lines 94, 159) and `mega_submenu.html` (line 16) use
   `{% if cat.get_children_count %}` to render expand buttons.
   `hasattr(Category, 'get_children_count')` returns False — MPTT provides
   get_children(), get_descendant_count(), but no get_children_count.
   Django templates return empty string for non-existent attributes, making the
   condition always False. Result: NO expand buttons render anywhere, so the
   accordion JS never fires. Can never navigate beyond level 1.

   RC-B: `{% firstof breadcrumb_category ad.category as current_cat %}` converts
   the Category object to a string.
   Django's FirstOfNode.render() calls render_value_in_context(value, context)
   which calls str() on the value before storing it. So current_cat becomes the
   string representation ("??????") instead of the Category object.
   Consequence: {{ current_cat.get_name }} renders empty (strings don't have
   get_name), and breadcrumb_category passed to the include is also a string,
   making get_ancestors and get_name fail silently.

   RC-C: `|last` filter on empty queryset raises ValueError.
   breadcrumb.html line 13:
   `{% with ancestors=...get_ancestors last_ancestor=...get_ancestors|last %}`
   For root categories, get_ancestors() returns empty queryset. Django's |last
   does value[-1] on the queryset, raising ValueError("Negative indexing is not
   supported."). The with-tag fails, inner breadcrumb content doesn't render.

   Runtime effects:
   - Home page: breadcrumb_category is None -> empty nav renders.
   - Category page: breadcrumb_category is Category object but firstof converts
     it to string -> only "???????" renders, no category path.
   - Ad detail: same firstof issue -> breadcrumb content fails.

2) Menu navigation only works at current level — cannot go deeper from level 2
   to 3, or from level 4 to level 3.

   Root Cause: RC-A — no expand buttons render at all (method does not exist).
   The accordion JS (closeBranch/collapseSiblings) was redesigned in commit
   2a72514 but has nothing to attach to without expand buttons.

Fix plan (see Decision_022):

   Fix RC-A: Replace {% if cat.get_children_count %} with
   {% if cat.get_children.exists %} in header_catalog.html and mega_submenu.html.
   Django chains .get_children (method call -> queryset) and .exists (method
   call -> boolean).

   Fix RC-B: Replace {% firstof ... as current_cat %} with explicit
   if/else + {% with %} to preserve the object reference.

   Fix RC-C: Replace |last on queryset with slice:"-1:"|first or length-
   based branching that handles empty querysets gracefully.

????? ????????? reseracher ???????, ???? ??????, ??? ???? ??????? ?? ????????? ? ????????? ???? ?????????
