/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 * Generated from: CanonicalOrder
 * Generator: schema-gen Zod generator
 *
 * To regenerate this file, run:
 *     schema-gen generate --target zod
 *
 * Changes to this file will be overwritten.
 */

import { z } from 'zod';

/** Two-sided trade direction. */
export const CanonicalSideSchema = z.enum(["buy", "sell"]);
export type CanonicalSide = z.infer<typeof CanonicalSideSchema>;

/**
 * Order placed against the matching engine.

Carries the instrument identifier, the side (BUY/SELL), and an optional
client-supplied tag. Used as a fixture for cross-generator output
stability tests.
 */
export const CanonicalOrderSchema = z.object({
  instrument: z.string(), // Exchange-prefixed symbol
  quantity: z.number().int(), // Number of contracts
  price: z.number(), // Limit price
  side: CanonicalSideSchema, // Buy or sell
  tag: z.string().optional(), // Optional client tag
  metadata: z.record(z.any()), // Free-form metadata
  fills: z.array(z.number()), // Per-fill prices (FIFO)
});

export type CanonicalOrder = z.infer<typeof CanonicalOrderSchema>;