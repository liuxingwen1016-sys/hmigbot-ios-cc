<!-- when: Phase A 生成 / 扩展 meta.json 时加载 -->
<!-- topics: meta.json, schema, layout_sources, dynamic_menus, bottom_sheet_config, navigation_mode -->

# meta.json 完整 schema

Phase A 为每个页面扩展 / 生成 meta.json。确定性字段由 `synthesize_meta_json.py` 填，语义字段由 LLM 补。完整字段示例：

同一 schema 也用于 `spec/baseline/dialog-snapshots/`：此时 `page_id` 存放稳定 snapshot ID（opaque
artifact id），`activity` 必须是 `layout_owner_fqn`，`page_type`/safe-area 来自确定性 Dialog
inventory。Dialog 是否属于页面清单不由 meta 文件存在与否决定。

```json
{
  "page_id": "page_0001_MainActivity",
  "label": "从 android:label 或源码注释推断的页面描述",
  "activity": "com.example.app.MainActivity",
  "auto_generated": true,
  "confidence": "high | medium | low",
  "layout_sources": [
    "app/src/main/res/layout/activity_main.xml",
    "app/src/main/res/layout/fragment_home.xml"
  ],
  "style_sources": [
    "app/src/main/res/values/styles.xml",
    "app/src/main/res/values/themes.xml",
    "app/src/main/res/values/colors.xml"
  ],
  "click_path": [],
  "came_from": null,
  "trigger_element": null,
  "clickable_elements": [
    {
      "class": "android.widget.Button",
      "resource_id": "com.example:id/btn_submit",
      "text": "Submit",
      "content_desc": "Submit button",
      "bounds": "[100,200][300,250]",
      "children_items": []
    }
  ],
  "navigation_targets": {
    "btn_settings": "SettingsActivity",
    "btn_profile": "ProfileFragment"
  },
  "menu_sources": ["app/src/main/res/menu/home.xml"],
  "fragment_tags": {"InboxFragment": "NewEpisodesFragment", "AllEpisodesFragment": "EpisodesFragment"},
  "dynamic_menus": {
    "bottom_nav": {
      "build_method": "BottomNavigation.buildMenu()",
      "max_visible_items": 4,
      "has_more_overflow": true,
      "more_popup_type": "ListPopupWindow",
      "configurable": true
    }
  },
  "bottom_sheet_config": {
    "behavior_class": "LockableBottomSheetBehavior",
    "peek_height_dimen": "external_player_height",
    "states": ["COLLAPSED", "EXPANDED", "HIDDEN"],
    "lockable": true
  },
  "recycler_item_layouts": [
    {"adapter": "NavListAdapter", "layouts": ["nav_listitem", "nav_section_item"]}
  ],
  "navigation_mode": "MUTUALLY_EXCLUSIVE",
  "page_type": "full_screen_page",
  "needs_immersive_safearea": true
}
```
