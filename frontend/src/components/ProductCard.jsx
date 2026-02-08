import React from 'react';
import { formatPrice } from '../lib/api';

export default function ProductCard({ product, mode, selected, onClick, compact = false }) {
  return (
    <button
      type="button"
      className={`product-card ${selected ? 'selected' : ''} ${compact ? 'compact' : ''}`}
      onClick={onClick}
    >
      <div className="thumb-wrap">
        {product.image_url ? (
          <img src={product.image_url} alt={product.title} loading="lazy" />
        ) : (
          <div className="image-fallback">No image</div>
        )}
      </div>
      <div className="card-content">
        <h3>{product.title}</h3>
        <p className="muted">{product.vendor || 'Unknown vendor'}</p>
        <p className="price">{formatPrice(product.price_min, product.price_max)}</p>
        {mode === 'feature' && (
          <div className="tag-list">
            {(product.tags || []).slice(0, 4).map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        )}
      </div>
    </button>
  );
}
