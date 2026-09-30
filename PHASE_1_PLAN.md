# Phase 1 Execution Plan — Core Stability & Accessibility

**Timeline**: 1 sprint (6 hours)  
**Goal**: Resolve all WCAG Level A violations + fix SQLite concurrency  
**Risk Window**: Daily backups during development  

---

## Priority 1: SQLite Concurrency Fix (2 hours)

**File**: `src/db/database.py`

**Current Problem**: `check_same_thread=False` allows unsafe concurrent writes from Flask's thread pool.

**Solution**: Add `threading.Lock()` wrapper around all DB operations.

```python
import threading

# At module level
_db_lock = threading.Lock()

# In Database class
def _execute_write(self, func, *args, **kwargs):
    """Wrapper for write operations — ensures only one thread touches DB at a time."""
    with _db_lock:
        return func(*args, **kwargs)

# Usage in Database methods
def set_manual_status(self, listing_id, status):
    return self._execute_write(self._set_manual_status_unlocked, listing_id, status)

def _set_manual_status_unlocked(self, listing_id, status):
    # Original implementation
    ...
```

**Testing**: 
- Load-test with concurrent requests (Apache Bench)
- Verify no UNIQUE constraint violations
- Check data integrity after 1000 concurrent requests

**Success Criteria**: 
- ✅ 1000 concurrent requests complete without data corruption
- ✅ Zero "database is locked" timeout errors (with reasonable 30s timeout)

---

## Priority 2: Image Alt Text (1 hour)

**Files**: `index.html`, `scripts/generate_dashboard.py`

**Problem**: All product images have empty `alt=""` attributes. Screen readers cannot identify e-bikes.

**Solution**: Auto-generate alt text from listing data.

```html
<!-- Before -->
<img src="photo.jpg" alt="">

<!-- After -->
<img src="photo.jpg" alt="Listing photo: Cannondale Habit Neo 4 (2023)">
```

**Implementation**:
1. Modify `generate_dashboard.py` render function to include brand/model/year in alt text
2. Fallback to portal name if brand/model missing
3. Example: `f"alt='{listing['brand']} {listing['model']} ({listing['year']})' or '{listing['portal']} listing'"`

**Testing**: 
- Run NVDA screen reader on 10 random listings
- Verify alt text is spoken and meaningful

**Success Criteria**:
- ✅ All 2144 listings have non-empty, descriptive alt text
- ✅ WCAG Level A: Image text alternative

---

## Priority 3: Modal ARIA & Focus Trap (2 hours)

**Files**: `index.html`, JavaScript modal handlers

**Problem**: Modal is not keyboard/screen-reader accessible.
- Missing `role="dialog"` and `aria-modal="true"`
- No focus trap (Tab can escape)
- ESC closes without user awareness
- No title linkage via `aria-labelledby`

**Solution**: Add ARIA attributes + JavaScript focus trap.

```html
<!-- Modal HTML -->
<div id="editModal" 
     role="dialog" 
     aria-modal="true" 
     aria-labelledby="modalTitle"
     tabindex="-1">
  <h2 id="modalTitle">Edit Listing Specifications</h2>
  <button id="modalCloseBtn" aria-label="Close dialog">✕</button>
  <!-- Modal content -->
</div>

<!-- Background overlay -->
<div id="modalOverlay" aria-hidden="true"></div>
```

**JavaScript Focus Trap**:
```javascript
function openModal() {
  modal.style.display = 'block';
  
  // Get all focusable elements
  const focusableElements = modal.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const firstEl = focusableElements[0];
  const lastEl = focusableElements[focusableElements.length - 1];
  
  // Focus first element on open
  firstEl.focus();
  
  // Trap Tab key
  modal.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    
    if (e.shiftKey) {
      if (document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      }
    } else {
      if (document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    }
  });
  
  // Handle ESC key
  modal.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModal();
    }
  });
}

function closeModal() {
  modal.style.display = 'none';
  // Return focus to triggering button (if available)
  document.getElementById('editBtn')?.focus();
}
```

**Testing**:
- Navigate modal using only keyboard (Tab, Shift+Tab, ESC)
- Verify focus stays within modal
- Test with NVDA/JAWS screen reader

**Success Criteria**:
- ✅ Keyboard-only user can open, navigate, and close modal
- ✅ Screen reader announces modal title and role
- ✅ Focus trap prevents accidental background interaction

---

## Priority 4: Filter Label Linking (0.5 hours)

**File**: `index.html`

**Problem**: Filter labels are not semantically linked to inputs. Screen readers cannot identify field purposes.

**Current**:
```html
<div class="filter-group">
  <label>Budget da (CHF)</label>
  <input type="number" id="priceMin">
</div>
```

**Fixed**:
```html
<div class="filter-group">
  <label for="priceMin">Budget da (CHF)</label>
  <input type="number" id="priceMin">
</div>
```

**Changes** (all filters):
1. Add `for="fieldId"` to every `<label>`
2. Ensure all inputs have matching `id` attribute
3. Remove duplicate labels (consolidate into one)

**Testing**:
- Use browser Inspector → Accessibility panel
- Verify label is associated with input
- Test with screen reader

**Success Criteria**:
- ✅ All 8+ filter inputs have linked labels
- ✅ Screen reader announces label when input is focused

---

## Priority 5: Color Contrast Fix (0.5 hours)

**File**: CSS in `index.html` (or extracted stylesheet)

**Problem**: Status badges fail WCAG AA (4.5:1 contrast required).

**Current**:
```css
.status.sold { background: #f3f4f6; color: #6b7280; }  /* 3.2:1 ❌ */
.status.rejected { background: #fecaca; color: #7f1d1d; }  /* 2.8:1 ❌ */
```

**Fixed** (high contrast):
```css
.status.sold { background: #1f2937; color: #fff; }  /* 12:1 ✅ */
.status.rejected { background: #7f1d1d; color: #fff; }  /* 8.5:1 ✅ */
.status.active { background: #065f46; color: #fff; }  /* High contrast */
```

**Testing**:
- Use WebAIM Contrast Checker
- Verify all badges meet 4.5:1 ratio

**Success Criteria**:
- ✅ All status badges meet WCAG AA (4.5:1)
- ✅ Low-vision users can read status clearly

---

## Priority 6: View Toggle Discoverability (0.5 hours)

**File**: `index.html`

**Problem**: Icon-only buttons (☰, ⊞) are cryptic. Mobile users cannot discover list/card toggle.

**Current**:
```html
<button id="viewListBtn" class="icon-btn">☰</button>
<button id="viewCardBtn" class="icon-btn">⊞</button>
```

**Fixed** (visible labels):
```html
<button id="viewListBtn" class="view-toggle-btn active" aria-label="Switch to list view">
  📋 <span class="btn-label">List</span>
</button>
<button id="viewCardBtn" class="view-toggle-btn" aria-label="Switch to card view">
  ⊞ <span class="btn-label">Card</span>
</button>
```

**CSS**:
```css
.btn-label {
  display: none;  /* Hidden on desktop */
}

@media (max-width: 768px) {
  .btn-label {
    display: inline;  /* Show on mobile */
  }
}
```

**Testing**:
- Desktop: Icon only (space-efficient)
- Mobile: Icon + text (discoverable)
- Test with keyboard navigation
- Test with touch on real device

**Success Criteria**:
- ✅ Mobile users can discover view toggle without tooltips
- ✅ Touch targets are >= 48x48px (or 44x44px minimum)
- ✅ Keyboard navigation works (Tab to button, Enter to activate)

---

## Daily Backup Strategy

**Automated Backup Script** (`.backups/backup.sh`):

```bash
#!/bin/bash
# Run daily before development starts

DB_FILE="./data/ebike_listings.db"
BACKUP_DIR="./.backups"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)

mkdir -p "$BACKUP_DIR"

# Copy current DB
cp "$DB_FILE" "$BACKUP_DIR/ebike-listings-${DATE}.db"

# Keep only 7-day rolling window
find "$BACKUP_DIR" -name "ebike-listings-*.db" -mtime +7 -delete

echo "✅ Backup created: $BACKUP_DIR/ebike-listings-${DATE}.db"
```

**Usage**:
```bash
# Before Phase 1 work each day
bash .backups/backup.sh

# If something goes wrong
cp .backups/ebike-listings-2026-09-30.db ./data/ebike_listings.db
```

---

## Success Criteria Checklist

After Phase 1, verify:

- [ ] SQLite lock prevents concurrent corruption (load-test passes)
- [ ] All 2144 listings have alt text
- [ ] Modal passes keyboard navigation + screen reader audit
- [ ] All filter inputs have linked labels (Accessibility Inspector confirms)
- [ ] Status badges meet WCAG AA contrast (4.5:1)
- [ ] View toggle is discoverable on mobile
- [ ] Daily backups run without error
- [ ] Zero data loss during Phase 1 development

---

## Timeline

| Task | Duration | Day |
|------|----------|-----|
| SQLite concurrency fix | 2 hrs | Day 1 (morning) |
| Image alt text | 1 hr | Day 1 (afternoon) |
| Modal ARIA + focus trap | 2 hrs | Day 2 (morning) |
| Filter labels + color contrast + view toggle | 1.5 hrs | Day 2 (afternoon) |
| Testing & QA | 1 hr | Day 3 |
| **Total** | **6 hrs** | **Next Sprint** |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Data loss during Phase 1 | Daily automated backups to `.backups/` |
| Concurrency fix breaks something | Run load test before shipping Phase 1 |
| Accessibility fixes introduce regressions | Manual smoke test on all endpoints |
| Focus trap breaks on old browsers | Progressive enhancement (works without JS) |

---

## Approved By

**Business Owner**: Conditional GO for internal MVP  
**Deadline**: Phase 1 locked in for next sprint  
**Risk Window**: Mitigated by daily backups + load testing
