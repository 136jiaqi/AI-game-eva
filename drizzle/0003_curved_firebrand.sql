CREATE TABLE `page_exposures` (
	`id` text PRIMARY KEY NOT NULL,
	`visitor_id` text NOT NULL,
	`phone` text DEFAULT '' NOT NULL,
	`path` text DEFAULT '' NOT NULL,
	`referrer` text DEFAULT '' NOT NULL,
	`user_agent` text DEFAULT '' NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `page_exposures_created_at_idx` ON `page_exposures` (`created_at`);--> statement-breakpoint
CREATE INDEX `page_exposures_visitor_id_idx` ON `page_exposures` (`visitor_id`);--> statement-breakpoint
CREATE INDEX `page_exposures_phone_idx` ON `page_exposures` (`phone`);--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `visitor_id` text DEFAULT '' NOT NULL;--> statement-breakpoint
CREATE INDEX `evaluation_records_visitor_id_idx` ON `evaluation_records` (`visitor_id`);
