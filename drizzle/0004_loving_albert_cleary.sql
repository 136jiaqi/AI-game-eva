CREATE TABLE `steam_game_overrides` (
	`appid` text PRIMARY KEY NOT NULL,
	`manual_passed` integer,
	`manual_reason` text DEFAULT '' NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `steam_game_queries` (
	`id` text PRIMARY KEY NOT NULL,
	`appid` text NOT NULL,
	`game_name_en` text DEFAULT '' NOT NULL,
	`game_name_zh` text DEFAULT '' NOT NULL,
	`app_type` text DEFAULT '' NOT NULL,
	`technologies` text DEFAULT '' NOT NULL,
	`release_date` text DEFAULT '' NOT NULL,
	`categories` text DEFAULT '' NOT NULL,
	`tag` text DEFAULT '' NOT NULL,
	`screenshots` text DEFAULT '' NOT NULL,
	`players_right_now` text DEFAULT '' NOT NULL,
	`peak_24h` text DEFAULT '' NOT NULL,
	`all_time_peak` text DEFAULT '' NOT NULL,
	`languages` text DEFAULT '' NOT NULL,
	`client_status` text DEFAULT '' NOT NULL,
	`client_development_status` text DEFAULT '' NOT NULL,
	`auto_passed` integer DEFAULT false NOT NULL,
	`final_passed` integer DEFAULT false NOT NULL,
	`manual_passed` integer,
	`manual_reason` text DEFAULT '' NOT NULL,
	`result_title` text DEFAULT '' NOT NULL,
	`result_detail` text DEFAULT '' NOT NULL,
	`reason` text DEFAULT '' NOT NULL,
	`raw_json` text DEFAULT '' NOT NULL,
	`queried_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `steam_game_queries_appid_idx` ON `steam_game_queries` (`appid`);--> statement-breakpoint
CREATE INDEX `steam_game_queries_queried_at_idx` ON `steam_game_queries` (`queried_at`);--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `result_title` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `result_detail` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `auto_passed` integer;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `manual_passed` integer;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `manual_reason` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `app_type` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `technologies` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `release_date` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `categories` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `tag` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `evaluation_records` ADD `screenshots` text DEFAULT '' NOT NULL;