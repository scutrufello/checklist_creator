-- Phillies Cards Database Schema
-- SQLite database for storing TCDB Phillies card data

-- Sets table to normalize set information
CREATE TABLE IF NOT EXISTS sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'main_set', 'subset', 'parallel'
    display_name TEXT NOT NULL,  -- Full display name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, name, type)
);

-- Cards table for individual card data
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    main_set_id INTEGER NOT NULL,
    subset_id INTEGER,  -- NULL if no subset
    card_number TEXT,
    player_name TEXT NOT NULL,
    card_title TEXT NOT NULL,  -- Full card title
    card_type TEXT,  -- RC, AU, RELIC, SN25, etc.
    front_image_path TEXT,
    back_image_path TEXT,
    tcdb_url TEXT NOT NULL,
    scraped_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (main_set_id) REFERENCES sets(id),
    FOREIGN KEY (subset_id) REFERENCES sets(id),
    UNIQUE(tcdb_url)
);

-- Card metadata table for additional attributes
CREATE TABLE IF NOT EXISTS card_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    metadata_type TEXT NOT NULL,  -- 'RC', 'AU', 'RELIC', 'SN', 'parallel', etc.
    metadata_value TEXT,  -- For SN cards: '25', for parallels: 'GOLD', etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id),
    UNIQUE(card_id, metadata_type, metadata_value)
);

-- Images table to track image files
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    image_type TEXT NOT NULL,  -- 'front', 'back'
    file_path TEXT NOT NULL,
    file_size INTEGER,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_cards_year ON cards(year);
CREATE INDEX IF NOT EXISTS idx_cards_main_set ON cards(main_set_id);
CREATE INDEX IF NOT EXISTS idx_cards_player ON cards(player_name);
CREATE INDEX IF NOT EXISTS idx_cards_type ON cards(card_type);
CREATE INDEX IF NOT EXISTS idx_sets_year_name ON sets(year, name);
CREATE INDEX IF NOT EXISTS idx_metadata_card_type ON card_metadata(card_id, metadata_type);
