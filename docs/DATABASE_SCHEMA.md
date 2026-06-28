# Database Schema Documentation

## Overview

EduSphere uses SQLite as its database backend. The database is automatically created on first run and stored in the `instance/` directory.

## Tables

### users

Stores user account information for all roles (admin, faculty, student).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| name | TEXT | User's full name |
| email | TEXT | User's email address (unique) |
| password | TEXT | Hashed password |
| role | TEXT | User role: 'admin', 'faculty', or 'student' |
| approved | INTEGER | Approval status: 0 (pending) or 1 (approved) |
| profile_completed | INTEGER | Profile completion status: 0 (incomplete) or 1 (complete) |
| phone | TEXT | Phone number (optional) |
| date_of_birth | TEXT | Date of birth (optional) |
| gender | TEXT | Gender (optional) |
| reg_number | TEXT | Registration number (students only) |
| program | TEXT | Program/course (students only) |
| section | TEXT | Section/batch (students only) |
| faculty_id | INTEGER | Faculty ID (for faculty profile) |
| designation | TEXT | Designation/title (faculty only) |
| subject | TEXT | Subject specialization (faculty only) |
| profile_image | TEXT | Profile image path |
| created_at | TEXT | Account creation timestamp |

### classrooms

Stores classroom/course information.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| name | TEXT | Classroom name |
| subject | TEXT | Subject taught |
| code | TEXT | Unique classroom code for enrollment |
| faculty_id | INTEGER | Faculty ID (foreign key to users) |
| description | TEXT | Classroom description |
| created_at | TEXT | Creation timestamp |
| is_archived | INTEGER | Archive status: 0 (active) or 1 (archived) |
| archived_at | TEXT | Archive timestamp |

### classroom_members

Stores student enrollment in classrooms.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| classroom_id | INTEGER | Classroom ID (foreign key) |
| student_id | INTEGER | Student ID (foreign key to users) |
| joined_at | TEXT | Enrollment timestamp |

### exams

Stores exam information.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| title | TEXT | Exam title |
| subject | TEXT | Subject |
| exam_date | TEXT | Exam date |
| duration | INTEGER | Duration in minutes |
| total_marks | INTEGER | Total marks |
| pass_percentage | INTEGER | Pass percentage threshold |
| faculty_id | INTEGER | Faculty ID (foreign key to users) |
| classroom_id | INTEGER | Classroom ID (foreign key, optional) |
| instructions | TEXT | Exam instructions |
| launched | INTEGER | Launch status: 0 (draft) or 1 (launched) |
| published | INTEGER | Results published status: 0 or 1 |
| created_at | TEXT | Creation timestamp |
| is_archived | INTEGER | Archive status: 0 (active) or 1 (archived) |
| archived_at | TEXT | Archive timestamp |

### questions

Stores questions for exams.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| exam_id | INTEGER | Exam ID (foreign key) |
| question | TEXT | Question text |
| option1 | TEXT | First option |
| option2 | TEXT | Second option |
| option3 | TEXT | Third option |
| option4 | TEXT | Fourth option |
| correct_answer | TEXT | Correct option (1-4) |
| difficulty | TEXT | Difficulty level: 'easy', 'medium', or 'hard' |
| marks | INTEGER | Marks for this question |

### question_bank

Stores reusable questions in the question bank.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| question | TEXT | Question text |
| option1 | TEXT | First option |
| option2 | TEXT | Second option |
| option3 | TEXT | Third option |
| option4 | TEXT | Fourth option |
| correct_answer | TEXT | Correct option (1-4) |
| category | TEXT | Question category |
| difficulty | TEXT | Difficulty level |
| faculty_id | INTEGER | Faculty ID (foreign key to users) |
| created_at | TEXT | Creation timestamp |

### submissions

Stores student exam submissions.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| student_id | INTEGER | Student ID (foreign key to users) |
| exam_id | INTEGER | Exam ID (foreign key) |
| score | INTEGER | Score obtained |
| tab_switches | INTEGER | Number of tab switches during exam |
| result_published | INTEGER | Result published status: 0 or 1 |
| published_at | TEXT | Publication timestamp |
| submitted_at | TEXT | Submission timestamp |

### submission_answers

Stores individual answers for each submission.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| submission_id | INTEGER | Submission ID (foreign key) |
| question_id | INTEGER | Question ID (foreign key) |
| student_answer | TEXT | Student's answer |

### activity_log

Stores user activity logs for auditing.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| user_id | INTEGER | User ID (foreign key to users) |
| action | TEXT | Action description |
| timestamp | TEXT | Action timestamp |

### exam_attempts

Stores in-progress exam attempts for auto-save functionality.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| student_id | INTEGER | Student ID (foreign key to users) |
| exam_id | INTEGER | Exam ID (foreign key) |
| current_question | INTEGER | Current question index |
| remaining_time | INTEGER | Remaining time in seconds |
| answers | TEXT | JSON string of answers |
| last_saved | TEXT | Last save timestamp |

## Relationships

- **users → classrooms**: One-to-many (faculty can create multiple classrooms)
- **users → classroom_members**: One-to-many (students can join multiple classrooms)
- **classrooms → classroom_members**: One-to-many (classroom can have many students)
- **classrooms → exams**: One-to-many (classroom can have many exams)
- **users → exams**: One-to-many (faculty can create multiple exams)
- **exams → questions**: One-to-many (exam can have many questions)
- **users → question_bank**: One-to-many (faculty can have many banked questions)
- **users → submissions**: One-to-many (student can have many submissions)
- **exams → submissions**: One-to-many (exam can have many submissions)
- **submissions → submission_answers**: One-to-many (submission can have many answers)
- **users → activity_log**: One-to-many (user can have many activity logs)
- **users → exam_attempts**: One-to-many (student can have in-progress attempts)
- **exams → exam_attempts**: One-to-many (exam can have in-progress attempts)

## Indexes

The following indexes are recommended for performance:

- `users.email` - Unique index for email lookups
- `classrooms.code` - Unique index for classroom code lookups
- `classroom_members.classroom_id` - Index for classroom member queries
- `classroom_members.student_id` - Index for student classroom queries
- `exams.faculty_id` - Index for faculty exam queries
- `exams.classroom_id` - Index for classroom exam queries
- `questions.exam_id` - Index for exam question queries
- `submissions.student_id` - Index for student submission queries
- `submissions.exam_id` - Index for exam submission queries
- `activity_log.user_id` - Index for user activity queries
- `activity_log.timestamp` - Index for timestamp-based queries
