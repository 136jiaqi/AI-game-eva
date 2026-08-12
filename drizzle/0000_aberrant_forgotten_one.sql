CREATE TABLE `evaluation_records` (
	`id` text PRIMARY KEY NOT NULL,
	`submitted_at` text NOT NULL,
	`store_url` text DEFAULT '' NOT NULL,
	`game_name` text DEFAULT '' NOT NULL,
	`steam_game_name` text DEFAULT '' NOT NULL,
	`appid` text DEFAULT '' NOT NULL,
	`phone` text DEFAULT '' NOT NULL,
	`requirements` text DEFAULT '' NOT NULL,
	`result` text DEFAULT 'fail' NOT NULL,
	`passed` integer DEFAULT false NOT NULL,
	`reason` text DEFAULT '' NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `evaluation_records_submitted_at_idx` ON `evaluation_records` (`submitted_at`);--> statement-breakpoint
CREATE INDEX `evaluation_records_phone_idx` ON `evaluation_records` (`phone`);--> statement-breakpoint
CREATE INDEX `evaluation_records_appid_idx` ON `evaluation_records` (`appid`);--> statement-breakpoint
CREATE INDEX `evaluation_records_game_name_idx` ON `evaluation_records` (`game_name`);