// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
// Generator: schema-gen Arrow (Rust) generator

use std::sync::Arc;

use arrow::datatypes::{DataType, Field, Schema, TimeUnit};

/// Arrow schema for `CanonicalOrder`, generated from its USR definition.
/// Order placed against the matching engine.
///
/// Carries the instrument identifier, the side (BUY/SELL), and an optional
/// client-supplied tag. Used as a fixture for cross-generator output
/// stability tests.
pub fn canonical_order_arrow_schema() -> Schema {
    let fields: Vec<Field> = vec![
        // Exchange-prefixed symbol
        Field::new("instrument", DataType::Utf8, false),
        // Number of contracts
        Field::new("quantity", DataType::Int64, false),
        // Limit price
        Field::new("price", DataType::Float64, false),
        // Buy or sell
        Field::new("side", DataType::Utf8, false),
        // Optional client tag
        Field::new("tag", DataType::Utf8, true),
        // Free-form metadata
        Field::new("metadata", DataType::LargeUtf8, false),
        // Per-fill prices (FIFO)
        Field::new("fills", DataType::List(Arc::new(Field::new("item", DataType::Float64, true))), false),
    ];
    Schema::new(fields).with_metadata(std::collections::HashMap::from([
        ("description".to_string(), "Order placed against the matching engine.\n\nCarries the instrument identifier, the side (BUY/SELL), and an optional\nclient-supplied tag. Used as a fixture for cross-generator output\nstability tests.".to_string()),
    ]))
}
