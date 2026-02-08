# MongoDB Migration Guide

This guide explains how to migrate from SQLite to MongoDB and use the new MongoDB-based backend.

## Why MongoDB?

MongoDB provides several advantages for this project:

1. **Flexible Schema**: Easy to store diverse product attributes without migrations
2. **Better for Sparse Data**: Collaborative filtering creates sparse matrices - MongoDB handles these naturally
3. **Scalability**: Built for horizontal scaling as the dataset grows
4. **Nested Documents**: Perfect for storing product images, tags, and options
5. **Async Operations**: Motor driver provides non-blocking async operations

## Installation

1. **Install MongoDB**:
   - Windows: Download from https://www.mongodb.com/try/download/community
   - Mac: `brew install mongodb-community`
   - Linux: Follow platform-specific instructions

2. **Install Python Dependencies**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Start MongoDB**:
   - Windows: Run MongoDB as a service or use `mongod --dbpath C:\data\db`
   - Mac/Linux: `brew services start mongodb-community` or `mongod`

## Configuration

1. Copy the example environment file:
   ```bash
   cp backend/.env.example backend/.env
   ```

2. Edit `backend/.env` to configure MongoDB connection:
   ```
   MONGODB_URL=mongodb://localhost:27017
   MONGODB_DB_NAME=decidio
   MONGODB_MAX_POOL_SIZE=10
   MONGODB_MIN_POOL_SIZE=1
   ```

## Migration Process

### Step 1: Run the Migration Script

The migration script will:
- Connect to your existing SQLite database
- Create MongoDB collections with indexes
- Migrate all data: products, users, sessions, selections, prefix_ratings
- Preserve all relationships between documents

```bash
cd backend
python -m backend.scripts.migrate_to_mongo
```

The script will show progress and print statistics:
```
Migrating products...
  Migrated product: TWSBI Eco ... (id: ...)
Migrated 153 products.

Migrating users...
  Migrated user: Test User ... (id: ...)
Migrated 5 users.

Final Statistics:
  Products: 153
  Users: 5
  Sessions: 20
  Selections: 85
  Prefix Ratings: 75
```

### Step 2: Verify Migration

Check MongoDB collections:
```bash
mongosh
use decidio
db.products.countDocuments()
db.users.countDocuments()
db.sessions.countDocuments()
db.selections.countDocuments()
db.prefix_ratings.countDocuments()
```

### Step 3: Run the MongoDB Backend

```bash
cd backend
# Run the MongoDB version
uvicorn app.main_mongo:app --reload --host 0.0.0.0 --port 8000
```

Or use the original SQLite version:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

The MongoDB backend maintains the same API endpoints:

- `GET /api/products` - List products (with filtering)
- `GET /api/products/{id}` - Get a specific product
- `POST /api/users` - Create a user
- `POST /api/sessions` - Create a session
- `POST /api/sessions/{id}/select` - Select a product
- `POST /api/sessions/{id}/rate` - Rate the current prefix
- `GET /api/sessions/{id}/recommendations` - Get recommendations
- `GET /api/debug/pbcf` - View PBCF model statistics

## Data Model

### Products Collection
```javascript
{
  "_id": ObjectId("..."),
  "source_id": "goulet-pens-123",
  "title": "TWSBI Eco",
  "vendor": "TWSBI",
  "product_type": "Fountain Pen",
  "price_min": 34.00,
  "price_max": 38.00,
  "currency": "USD",
  "tags": ["demonstrator", "piston-fill"],
  "options": {
    "color": ["Clear", "Blue", "Carmine"],
    "nib": ["EF", "F", "M", "B", "Stub"]
  },
  "description": "...",
  "url": "https://...",
  "images": [
    {
      "url": "https://...",
      "alt": "TWSBI Eco front view",
      "position": 0
    }
  ],
  "created_at": ISODate("2025-01-15T10:30:00Z")
}
```

### Users Collection
```javascript
{
  "_id": ObjectId("..."),
  "name": "John Doe",
  "sessions": [ObjectId("..."), ObjectId("...")],
  "created_at": ISODate("2025-01-15T10:30:00Z")
}
```

### Sessions Collection
```javascript
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "state": {
    "user_vec": [0.1, 0.2, ...],
    "bias": 0.5,
    "count": 3
  },
  "selections": [ObjectId("..."), ObjectId("...")],
  "prefix_ratings": [ObjectId("...")],
  "created_at": ISODate("2025-01-15T10:30:00Z")
}
```

### Selections Collection
```javascript
{
  "_id": ObjectId("..."),
  "session_id": ObjectId("..."),
  "product_id": ObjectId("..."),
  "is_exception": false,
  "created_at": ISODate("2025-01-15T10:30:00Z")
}
```

### Prefix Ratings Collection
```javascript
{
  "_id": ObjectId("..."),
  "session_id": ObjectId("..."),
  "rating": 4,
  "tags": ["demonstrator", "piston-fill"],
  "created_at": ISODate("2025-01-15T10:30:00Z")
}
```

## Performance Tips

### Indexes

The migration script creates these indexes automatically:
- `products.source_id` (unique)
- `products.title`
- `products.vendor`
- `users.name`

Add more indexes as needed:
```javascript
db.products.createIndex({ "price_min": 1 })
db.products.createIndex({ "tags": 1 })
db.sessions.createIndex({ "user_id": 1 })
db.selections.createIndex({ "session_id": 1 })
```

### Query Optimization

For large datasets, consider:
1. Adding appropriate indexes for common queries
2. Using MongoDB's aggregation pipeline for complex queries
3. Implementing pagination for list endpoints
4. Using projection to limit returned fields

## Troubleshooting

### MongoDB Connection Failed

```
pymongo.errors.ServerSelectionTimeoutError: No servers found
```

**Solution**: Make sure MongoDB is running:
```bash
# Check if MongoDB is running
mongosh --eval "db.adminCommand('ping')"

# Start MongoDB if needed
mongod --dbpath /path/to/data
```

### Migration Errors

If migration fails:
1. Check SQLite database exists: `ls -la data/decidio.db`
2. Verify MongoDB is running
3. Drop collections and retry:
   ```javascript
   use decidio
   db.products.drop()
   db.users.drop()
   db.sessions.drop()
   db.selections.drop()
   db.prefix_ratings.drop()
   ```

### Pydantic Validation Errors

If you see validation errors after migration:
1. Check that all required fields are present
2. Verify data types match the models
3. Check the MongoDB document structure

## File Structure

```
backend/
├── app/
│   ├── db.py              # SQLite database (old)
│   ├── db_mongo.py        # MongoDB database (new)
│   ├── models.py          # SQLAlchemy models (old)
│   ├── models_mongo.py    # Pydantic models for MongoDB (new)
│   ├── main.py            # FastAPI with SQLite (old)
│   ├── main_mongo.py      # FastAPI with MongoDB (new)
│   ├── schemas.py         # Updated schemas for MongoDB
│   ├── services/
│   │   ├── recommender.py      # SQLite recommender (old)
│   │   └── recommender_mongo.py # MongoDB recommender (new)
│   └── ml/
│       ├── prefix_cf.py    # Updated for both SQL and Mongo
│       ├── pbcf_nmf.py     # PBCF with SQLAlchemy (old)
│       └── pbcf_nmf_mongo.py # PBCF with MongoDB (new)
├── scripts/
│   ├── load_db.py         # Load SQLite database (old)
│   └── migrate_to_mongo.py # Migration script (new)
└── requirements.txt       # Updated dependencies
```

## Next Steps

After migration:

1. **Test thoroughly**: Verify all endpoints work correctly
2. **Monitor performance**: Check query times and add indexes as needed
3. **Implement the game**: Use the MongoDB backend for the new guessing game feature
4. **Scale up**: Add more products and user data
5. **Backup strategy**: Set up MongoDB backups

## Reverting to SQLite

If needed, you can still run the SQLite version:
```bash
uvicorn app.main:app --reload
```

The SQLite database remains untouched at `data/decidio.db`.
