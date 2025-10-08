# Frontend Testing Guide

This document explains how to run and write tests for the Signal Analytics Dashboard frontend.

## Setup

Install test dependencies:

```bash
cd frontend
npm install
```

This will install:
- **Vitest** - Fast unit test framework (Vite-native)
- **@vue/test-utils** - Vue component testing utilities
- **@vitest/ui** - Visual test interface
- **@vitest/coverage-v8** - Code coverage reporting
- **jsdom** - DOM simulation for Node.js
- **happy-dom** - Alternative DOM simulation (faster)

## Running Tests

### Run all tests once
```bash
npm run test
```

### Watch mode (re-runs tests on file changes)
```bash
npm run test:watch
```

### Visual UI (opens browser interface)
```bash
npm run test:ui
```

### Generate coverage report
```bash
npm run test:coverage
```

Coverage reports are generated in `coverage/` directory and displayed in the terminal.

## Test Structure

### Store Tests
Location: `src/stores/__tests__/`

These test the Pinia store logic in isolation (no DOM, no components).

**Example: `selection.test.js`**
- Tests signal selection/deselection
- Tests XD segment selection/deselection
- Tests overlapping XD segments between signals
- Tests computed properties

### Component Tests
Location: `src/components/__tests__/`

These test Vue component behavior with mocked dependencies.

**Example: `SharedMap.test.js`**
- Tests signal marker click handlers
- Tests XD segment click handlers
- Tests event emissions
- Tests component props and state integration

### Test Utilities
Location: `src/test-utils/index.js`

Shared helpers for test setup:
- `setupTestPinia()` - Creates isolated Pinia instance
- `createMockSignal()` - Factory for test signal data
- `createMultiXdSignal()` - Creates signals with multiple XD segments
- `createOverlappingSignals()` - Creates signals with shared XD segments
- Mock Leaflet objects for component testing

## Writing Tests

### Basic Store Test

```javascript
import { describe, it, expect, beforeEach } from 'vitest'
import { useMyStore } from '../myStore'
import { setupTestPinia } from '@/test-utils'

describe('My Store', () => {
  let store

  beforeEach(() => {
    setupTestPinia()
    store = useMyStore()
  })

  it('should do something', () => {
    store.someAction()
    expect(store.someState).toBe(expectedValue)
  })
})
```

### Basic Component Test

```javascript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import MyComponent from '../MyComponent.vue'

describe('MyComponent', () => {
  it('should render', () => {
    const wrapper = mount(MyComponent, {
      props: { /* props */ },
      global: {
        plugins: [createPinia()],
      },
    })

    expect(wrapper.exists()).toBe(true)
  })
})
```

## What's Tested

### Map Interaction Tests

The test suite comprehensively covers all map selection logic:

✅ **Signal Selection**
- Clicking signal selects it and all associated XD segments
- Multiple signals can be selected simultaneously
- Deselecting signal removes its XD segments

✅ **XD Segment Selection**
- XD segments can be selected independently
- XD segments can be deselected independently
- Direct XD selection works without signal selection

✅ **Overlapping XD Segments (Critical)**
- Shared XD segments between signals handled correctly
- Deselecting one signal doesn't remove shared XD if another signal still selected
- Complex selection/deselection scenarios tested

✅ **Chart Filtering**
- Selected XD segments provided for chart data filtering
- All selected XD segments included (from signals + direct selection)

✅ **Clear Selections**
- Clear all button removes all signal and XD selections
- State returns to empty

✅ **Edge Cases**
- Empty signals array
- Signals with null/undefined XD values
- Signals without valid coordinates
- Rapid selection/deselection

## Configuration

### vitest.config.js

Main configuration:
- **environment**: `jsdom` - Simulates browser DOM in Node.js
- **globals**: `true` - Auto-imports test functions (describe, it, expect)
- **coverage**: v8 provider with HTML reports
- **alias**: `@/` → `src/` for import paths

## Continuous Integration

To add tests to CI/CD pipeline:

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: |
    cd frontend
    npm install
    npm run test:coverage
```

## Tips

1. **Test Isolation**: Each test gets a fresh Pinia instance via `setupTestPinia()`
2. **Mock External Dependencies**: Leaflet is mocked to avoid real map rendering
3. **Use Test Utilities**: Leverage helper functions for consistent test data
4. **Watch Mode**: Use `npm run test:watch` during development for instant feedback
5. **Coverage**: Aim for >80% coverage on store logic, >60% on components

## Troubleshooting

### Tests fail with "Cannot find module"
- Ensure `npm install` completed successfully
- Check path aliases in `vitest.config.js`

### Tests timeout
- Increase timeout in `vitest.config.js`: `testTimeout: 20000`
- Check for async operations not being awaited

### Mock issues
- Verify mocks are defined before imports
- Use `vi.mock()` at top of test file

## Further Reading

- [Vitest Documentation](https://vitest.dev/)
- [Vue Test Utils](https://test-utils.vuejs.org/)
- [Pinia Testing](https://pinia.vuejs.org/cookbook/testing.html)
