# Valdi Component Patterns

Advanced patterns for building Valdi components.

## State Management

### ViewModel Pattern

Components use typed ViewModels for state:

```tsx
interface CounterViewModel {
  count: number;
  label: string;
}

class Counter extends Component<CounterViewModel, ComponentContext> {
  private updateCount(delta: number): void {
    this.viewModel.count += delta;
    this.requestRender();
  }

  onRender() {
    return (
      <layout style={styles.row}>
        <label onTap={() => this.updateCount(-1)}>-</label>
        <label>{this.viewModel.count}</label>
        <label onTap={() => this.updateCount(1)}>+</label>
      </layout>
    );
  }
}
```

### Observable State with RxJS

```tsx
import { BehaviorSubject } from 'rxjs';

interface UserViewModel {
  user$: BehaviorSubject<User | null>;
}

class UserProfile extends Component<UserViewModel, ComponentContext> {
  onCreate() {
    this.viewModel.user$.subscribe(user => {
      if (user) {
        this.requestRender();
      }
    });
  }

  onRender() {
    const user = this.viewModel.user$.getValue();
    return (
      <view>
        <label>{user?.name ?? 'Loading...'}</label>
      </view>
    );
  }
}
```

## Component Composition

### Child Components

```tsx
class ParentComponent extends Component<ParentViewModel, ComponentContext> {
  onRender() {
    return (
      <layout style={styles.container}>
        <Header title={this.viewModel.title} />
        <ContentList items={this.viewModel.items} />
        <Footer />
      </layout>
    );
  }
}
```

### Slots for Content Projection

```tsx
class Card extends Component<CardViewModel, ComponentContext> {
  onRender() {
    return (
      <view style={styles.card}>
        <view style={styles.header}>
          <slot name="header" />
        </view>
        <view style={styles.body}>
          <slot name="content" />
        </view>
      </view>
    );
  }
}

// Usage
<Card>
  <view slot="header">
    <label>Card Title</label>
  </view>
  <view slot="content">
    <label>Card body content here</label>
  </view>
</Card>
```

## Event Handling

### Touch Events

```tsx
class Button extends Component<ButtonViewModel, ComponentContext> {
  private handleTap = (): void => {
    this.viewModel.onPress?.();
  };

  private handleLongPress = (): void => {
    this.viewModel.onLongPress?.();
  };

  onRender() {
    return (
      <view
        style={styles.button}
        onTap={this.handleTap}
        onLongPress={this.handleLongPress}
      >
        <label style={styles.buttonText}>{this.viewModel.label}</label>
      </view>
    );
  }
}
```

### Gesture Handling

```tsx
class SwipeableCard extends Component<CardViewModel, ComponentContext> {
  private handleSwipe = (direction: 'left' | 'right'): void => {
    if (direction === 'left') {
      this.viewModel.onDismiss?.();
    } else {
      this.viewModel.onSave?.();
    }
  };

  onRender() {
    return (
      <view
        style={styles.card}
        onSwipeLeft={() => this.handleSwipe('left')}
        onSwipeRight={() => this.handleSwipe('right')}
      >
        {/* Card content */}
      </view>
    );
  }
}
```

## Lists and Scrolling

### Scroll Views

```tsx
class ScrollableList extends Component<ListViewModel, ComponentContext> {
  onRender() {
    return (
      <scroll style={styles.scrollContainer}>
        <layout style={styles.list}>
          {this.viewModel.items.map((item, index) => (
            <ListItem key={item.id} item={item} />
          ))}
        </layout>
      </scroll>
    );
  }
}
```

### Efficient List Rendering

Valdi automatically recycles views. For best performance:

```tsx
class EfficientList extends Component<ListViewModel, ComponentContext> {
  onRender() {
    return (
      <scroll
        style={styles.container}
        // Enable viewport-aware rendering
        viewportAware={true}
      >
        {this.viewModel.items.map(item => (
          <ListItem
            key={item.id}  // Always provide stable keys
            item={item}
          />
        ))}
      </scroll>
    );
  }
}
```

## Conditional Rendering

```tsx
class ConditionalView extends Component<ViewModel, ComponentContext> {
  onRender() {
    const { isLoading, hasError, data } = this.viewModel;

    if (isLoading) {
      return <LoadingSpinner />;
    }

    if (hasError) {
      return <ErrorView message={this.viewModel.errorMessage} />;
    }

    return (
      <view style={styles.content}>
        <DataDisplay data={data} />
      </view>
    );
  }
}
```

## Styling Patterns

### Style Objects

```tsx
const styles = {
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    padding: 16,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  text: {
    fontSize: 16,
    color: '#333333',
    fontWeight: '500',
  },
  title: {
    fontSize: 24,
    color: '#000000',
    fontWeight: 'bold',
  },
};
```

### Dynamic Styles

```tsx
class DynamicStyleComponent extends Component<ViewModel, ComponentContext> {
  private getButtonStyle() {
    return {
      ...styles.button,
      backgroundColor: this.viewModel.isActive ? '#007AFF' : '#CCCCCC',
      opacity: this.viewModel.isDisabled ? 0.5 : 1,
    };
  }

  onRender() {
    return (
      <view style={this.getButtonStyle()}>
        <label>{this.viewModel.label}</label>
      </view>
    );
  }
}
```

## Navigation

### Basic Navigation

```tsx
import { Navigator } from 'valdi_navigation';

class HomeScreen extends Component<HomeViewModel, ComponentContext> {
  private navigateToDetails = (itemId: string): void => {
    Navigator.push('DetailsScreen', { itemId });
  };

  private navigateBack = (): void => {
    Navigator.pop();
  };

  onRender() {
    return (
      <view>
        <label onTap={() => this.navigateToDetails('123')}>
          Go to Details
        </label>
      </view>
    );
  }
}
```

## Data Fetching

### HTTP Requests

```tsx
import { HttpClient } from 'valdi_http';

class DataComponent extends Component<DataViewModel, ComponentContext> {
  async onCreate() {
    try {
      const response = await HttpClient.get<ApiResponse>('/api/data');
      this.viewModel.data = response.data;
      this.requestRender();
    } catch (error) {
      this.viewModel.error = error.message;
      this.requestRender();
    }
  }

  onRender() {
    // Render based on viewModel.data or viewModel.error
  }
}
```

## Persistent Storage

```tsx
import { Storage } from 'valdi_storage';

class SettingsComponent extends Component<SettingsViewModel, ComponentContext> {
  async onCreate() {
    const savedTheme = await Storage.get('user_theme');
    this.viewModel.theme = savedTheme ?? 'light';
  }

  private async saveTheme(theme: string): Promise<void> {
    await Storage.set('user_theme', theme);
    this.viewModel.theme = theme;
    this.requestRender();
  }
}
```

## Performance Tips

1. **Minimize re-renders**: Only call `requestRender()` when necessary
2. **Use stable keys**: Always provide unique, stable keys for list items
3. **Memoize expensive computations**: Cache computed values
4. **Leverage viewport-aware rendering**: For long lists
5. **Keep components focused**: Small, single-purpose components

## Common Patterns Summary

| Pattern | Use Case |
|---------|----------|
| ViewModel | Component state management |
| RxJS Observables | Reactive state updates |
| Slots | Content projection/composition |
| Conditional rendering | Loading/error states |
| Dynamic styles | Theme/state-based styling |
| Navigator | Screen navigation |
| HttpClient | API requests |
| Storage | Persistent data |
