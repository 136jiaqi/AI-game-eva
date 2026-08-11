ALTER TABLE `evaluation_records` ADD COLUMN `payment_clicked` integer DEFAULT false NOT NULL;
--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD COLUMN `payment_clicked_at` text DEFAULT '' NOT NULL;
