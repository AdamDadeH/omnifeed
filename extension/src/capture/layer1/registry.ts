/**
 * Adapter Registry
 * Manages platform adapters and selects appropriate adapter for URLs
 */

import type { PlatformAdapter } from './interface';

export class AdapterRegistry {
  private adapters: PlatformAdapter[] = [];
  private adapterByDomain: Map<string, PlatformAdapter> = new Map();
  private genericAdapter: PlatformAdapter | null = null;

  /**
   * Register a platform adapter
   */
  register(adapter: PlatformAdapter): void {
    this.adapters.push(adapter);

    // Index by domain for fast lookup
    for (const domain of adapter.domains) {
      if (domain !== '*') {
        this.adapterByDomain.set(domain, adapter);
      }
    }

    // Track generic adapter
    if (adapter.platformId === 'generic') {
      this.genericAdapter = adapter;
    }
  }

  /**
   * Find adapter for URL
   */
  findAdapter(url: string): PlatformAdapter | null {
    try {
      const urlObj = new URL(url);
      const hostname = urlObj.hostname.replace(/^www\./, '');

      // Fast path: exact domain match
      const indexed = this.adapterByDomain.get(hostname);
      if (indexed && indexed.canHandle(url)) {
        return indexed;
      }

      // Check parent domains
      const parts = hostname.split('.');
      for (let i = 1; i < parts.length; i++) {
        const parent = parts.slice(i).join('.');
        const parentAdapter = this.adapterByDomain.get(parent);
        if (parentAdapter && parentAdapter.canHandle(url)) {
          return parentAdapter;
        }
      }

      // Slow path: check all adapters
      for (const adapter of this.adapters) {
        if (adapter.platformId !== 'generic' && adapter.canHandle(url)) {
          return adapter;
        }
      }

      // Fall back to generic adapter
      return this.genericAdapter;
    } catch {
      return this.genericAdapter;
    }
  }

  /**
   * Get all registered platform IDs (excluding generic)
   */
  getPlatformIds(): string[] {
    return this.adapters
      .filter((a) => a.platformId !== 'generic')
      .map((a) => a.platformId);
  }

  /**
   * Get all registered adapters
   */
  getAdapters(): PlatformAdapter[] {
    return [...this.adapters];
  }

  /**
   * Check if platform is supported
   */
  isSupported(platformId: string): boolean {
    return this.adapters.some((a) => a.platformId === platformId);
  }

  /**
   * Get adapter by platform ID
   */
  getAdapter(platformId: string): PlatformAdapter | null {
    return this.adapters.find((a) => a.platformId === platformId) ?? null;
  }
}

// Singleton registry
let registryInstance: AdapterRegistry | null = null;

export function getAdapterRegistry(): AdapterRegistry {
  if (!registryInstance) {
    registryInstance = new AdapterRegistry();
  }
  return registryInstance;
}

/**
 * Initialize registry with all adapters
 * Called once at startup
 */
export async function initializeRegistry(): Promise<AdapterRegistry> {
  const registry = getAdapterRegistry();

  // Import adapters dynamically to avoid circular dependencies
  const { YouTubeAdapter } = await import('./youtube');
  const { GenericAdapter } = await import('./generic');

  // Register adapters (order matters - specific first)
  registry.register(new YouTubeAdapter());
  // registry.register(new NetflixAdapter());
  // registry.register(new SpotifyAdapter());
  // registry.register(new MediumAdapter());

  // Generic is always last
  registry.register(new GenericAdapter());

  return registry;
}
