// React 19's `@types/react` removed the legacy global `JSX` namespace in favour
// of `React.JSX`. This codebase annotates component return types as bare
// `JSX.Element` in ~120 places and previously only compiled because a transitive
// dependency re-declared the global namespace. Re-establish that global as an
// explicit alias of `React.JSX` so the contract no longer depends on a
// third-party side effect.
//
// TODO(frontend): migrate the bare `JSX.Element` annotations to `React.JSX.Element`
// (or drop them and rely on inference) and delete this shim.
import type * as React from 'react'

declare global {
  // biome-ignore lint/style/useNamingConvention: "JSX" is a TypeScript-mandated global namespace name
  namespace JSX {
    type ElementType = React.JSX.ElementType
    type Element = React.JSX.Element
    type ElementClass = React.JSX.ElementClass
    type ElementAttributesProperty = React.JSX.ElementAttributesProperty
    type ElementChildrenAttribute = React.JSX.ElementChildrenAttribute
    type LibraryManagedAttributes<C, P> = React.JSX.LibraryManagedAttributes<C, P>
    type IntrinsicAttributes = React.JSX.IntrinsicAttributes
    type IntrinsicClassAttributes<T> = React.JSX.IntrinsicClassAttributes<T>
    type IntrinsicElements = React.JSX.IntrinsicElements
  }
}
