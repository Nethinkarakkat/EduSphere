# API Documentation

## Overview

EduSphere provides a RESTful API for various operations. This document describes the available API endpoints.

## Base URL

```
http://localhost:5000
```

## Authentication

Most endpoints require session-based authentication. Users must be logged in to access protected routes.

## Endpoints

### Authentication

#### POST /login
Authenticate a user.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "password",
  "role": "student"
}
```

**Response:** Redirects to appropriate dashboard or returns error

---

#### POST /signup
Register a new user.

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "password",
  "confirm_password": "password",
  "role": "student"
}
```

**Response:** Redirects to login or returns error

---

#### GET /logout
Logout current user.

**Response:** Redirects to home page

---

### Auto-Save API

#### POST /api/auto_save_exam
Auto-save in-progress exam attempt.

**Headers:**
- Content-Type: application/json

**Request Body:**
```json
{
  "exam_id": 1,
  "current_question": 0,
  "remaining_time": 1800,
  "answers": {
    "1": "2",
    "2": "3"
  }
}
```

**Response:**
```json
{
  "success": true
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error message"
}
```

---

## Student Endpoints

### GET /student
Student dashboard.

**Response:** Renders student dashboard with available exams, upcoming exams, and recent results

---

### GET /student/analytics
Student performance analytics.

**Query Parameters:**
- None

**Response:** Renders analytics page with performance statistics

---

### GET /student/exams
List available and completed exams for student.

**Response:** Renders exams page with available and completed exams

---

### GET /student/classrooms
List student's enrolled classrooms.

**Response:** Renders classrooms page

---

### GET /student/classroom/<classroom_id>
View classroom details.

**URL Parameters:**
- classroom_id: Classroom ID

**Response:** Renders classroom detail page with exams and submissions

---

### GET /exam_instructions/<exam_id>
View exam instructions before attempting.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders exam instructions page

---

### POST /attempt/<exam_id>
Attempt an exam.

**URL Parameters:**
- exam_id: Exam ID

**Request Body:**
- Form data with answers for each question
- tab_switches: Number of tab switches

**Response:** Redirects to result page

---

### GET /view_result/<exam_id>
View exam result.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders result page if published, otherwise shows not published page

---

### GET /view_validation/<exam_id>
View submission validation.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders validation page with student answers

---

### POST /join_classroom
Join a classroom using code.

**Request Body:**
```json
{
  "code": "CLASS123"
}
```

**Response:** Redirects to classrooms page or shows error

---

### GET /student/profile
View student profile.

**Response:** Renders profile page

---

### POST /student/change_password
Change student password.

**Request Body:**
```json
{
  "current_password": "oldpass",
  "new_password": "newpass",
  "confirm_password": "newpass"
}
```

**Response:** Redirects with success or error message

---

## Faculty Endpoints

### GET /faculty
Faculty dashboard.

**Response:** Renders faculty dashboard with exams, classrooms, and statistics

---

### GET /faculty/exams
List faculty's exams.

**Query Parameters:**
- status: Filter by status (optional)

**Response:** Renders exams page

---

### GET /faculty/results
View exam results.

**Query Parameters:**
- subject: Filter by subject (optional)
- classroom: Filter by classroom (optional)
- exam: Filter by exam (optional)
- date_from: Filter by start date (optional)
- date_to: Filter by end date (optional)
- result: Filter by result status (optional)
- search: Search query (optional)

**Response:** Renders results page with filters

---

### GET /faculty/analytics
View faculty analytics.

**Query Parameters:**
- exam: Filter by exam (optional)
- classroom: Filter by classroom (optional)
- subject: Filter by subject (optional)

**Response:** Renders analytics page with charts and statistics

---

### GET /faculty/analytics/export
Export analytics to CSV.

**Query Parameters:**
- Same as /faculty/analytics

**Response:** CSV file download

---

### GET /faculty/analytics/export/pdf
Export analytics to PDF.

**Query Parameters:**
- Same as /faculty/analytics

**Response:** PDF file download

---

### GET /faculty/classrooms
List faculty's classrooms.

**Response:** Renders classrooms page

---

### POST /classrooms/create
Create a new classroom.

**Request Body:**
```json
{
  "name": "Physics 101",
  "subject": "Physics",
  "description": "Introduction to Physics"
}
```

**Response:** Redirects to classrooms page

---

### GET /classrooms/<cid>
View classroom details.

**URL Parameters:**
- cid: Classroom ID

**Response:** Renders classroom detail page

---

### POST /classrooms/<cid>/edit
Edit classroom.

**URL Parameters:**
- cid: Classroom ID

**Request Body:**
```json
{
  "name": "Updated Name",
  "subject": "Updated Subject",
  "description": "Updated Description"
}
```

**Response:** Redirects to classroom detail page

---

### POST /classrooms/<cid>/delete
Delete classroom.

**URL Parameters:**
- cid: Classroom ID

**Response:** Redirects to classrooms page

---

### GET /preview_exam/<exam_id>
Preview exam before launching.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders exam preview page

---

### POST /create_exam
Create a new exam.

**Request Body:**
```json
{
  "title": "Midterm Exam",
  "subject": "Physics",
  "exam_date": "2024-12-01",
  "duration": 60,
  "pass_percentage": 50,
  "classroom_id": 1,
  "instructions": "Exam instructions here"
}
```

**Response:** Redirects to exams page

---

### POST /edit_exam/<exam_id>
Edit exam details.

**URL Parameters:**
- exam_id: Exam ID

**Request Body:**
- Same as create_exam

**Response:** Redirects to exams page

---

### POST /delete_exam/<exam_id>
Delete exam.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Redirects to exams page

---

### GET /add_questions/<exam_id>
Add questions to exam.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders add questions page

---

### POST /add_questions/<exam_id>
Submit new question.

**URL Parameters:**
- exam_id: Exam ID

**Request Body:**
```json
{
  "question": "Question text",
  "o1": "Option 1",
  "o2": "Option 2",
  "o3": "Option 3",
  "o4": "Option 4",
  "answer": "1",
  "difficulty": "medium",
  "marks": 5
}
```

**Response:** Redirects to add questions page

---

### GET /select_questions/<exam_id>
Select questions from question bank.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders question bank selection page

---

### POST /select_questions/<exam_id>
Add selected questions to exam.

**URL Parameters:**
- exam_id: Exam ID

**Request Body:**
- Form data with selected question IDs

**Response:** Redirects to add questions page

---

### GET /view_questions/<exam_id>
View exam questions.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders questions view page

---

### GET /edit_questions/<exam_id>
Edit exam questions.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Renders questions edit page

---

### POST /edit_questions/<exam_id>
Update questions.

**URL Parameters:**
- exam_id: Exam ID

**Request Body:**
- Form data with updated question details

**Response:** Redirects to view questions page

---

### GET /launch_exam/<exam_id>
Launch exam for students.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Redirects to exams page

---

### GET /publish_results/<exam_id>
Publish exam results.

**URL Parameters:**
- exam_id: Exam ID

**Response:** Redirects to results page

---

### GET /question_bank
View question bank.

**Query Parameters:**
- q: Search query (optional)
- category: Filter by category (optional)

**Response:** Renders question bank page

---

### POST /add_bank_question
Add question to bank.

**Request Body:**
```json
{
  "question": "Question text",
  "o1": "Option 1",
  "o2": "Option 2",
  "o3": "Option 3",
  "o4": "Option 4",
  "answer": "1",
  "category": "Physics",
  "difficulty": "medium"
}
```

**Response:** Redirects to question bank

---

### GET /edit_bank_question/<id>
Edit banked question.

**URL Parameters:**
- id: Question ID

**Response:** Renders edit page

---

### POST /edit_bank_question/<id>
Update banked question.

**URL Parameters:**
- id: Question ID

**Request Body:**
- Same as add_bank_question

**Response:** Redirects to question bank

---

### GET /delete_bank_question/<id>
Delete banked question.

**URL Parameters:**
- id: Question ID

**Response:** Redirects to question bank

---

### GET /faculty/archive
View archived items.

**Response:** Renders archive page with archived classrooms and exams

---

### GET /faculty/profile
View faculty profile.

**Response:** Renders profile page

---

### POST /faculty/change_password
Change faculty password.

**Request Body:**
```json
{
  "current_password": "oldpass",
  "new_password": "newpass",
  "confirm_password": "newpass"
}
```

**Response:** Redirects with success or error message

---

## Admin Endpoints

### GET /admin
Admin dashboard.

**Response:** Renders admin dashboard with statistics

---

### GET /admin/users
List all users.

**Query Parameters:**
- q: Search query (optional)
- role_f: Filter by role (optional)
- status_f: Filter by status (optional)
- sort: Sort order (optional)

**Response:** Renders users page

---

### POST /admin/users
Add new user.

**Request Body:**
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "password": "password",
  "role": "faculty"
}
```

**Response:** Redirects to users page

---

### GET /admin/users/export
Export users to CSV.

**Response:** CSV file download

---

### GET /view_user/<id>
View user details.

**URL Parameters:**
- id: User ID

**Response:** Renders user detail page

---

### POST /edit_user/<id>
Edit user details.

**URL Parameters:**
- id: User ID

**Request Body:**
- User details fields

**Response:** Redirects to user detail page

---

### POST /delete_user/<id>
Delete user.

**URL Parameters:**
- id: User ID

**Response:** Redirects to users page

---

### POST /approve_user/<id>
Approve faculty user.

**URL Parameters:**
- id: User ID

**Response:** Redirects to users page

---

### GET /admin/activity
View activity log.

**Query Parameters:**
- search: Search query (optional)
- role: Filter by role (optional)
- from_date: Filter by start date (optional)
- to_date: Filter by end date (optional)

**Response:** Renders activity log page

---

### GET /admin/classrooms
View all classrooms.

**Response:** Renders classrooms page

---

### GET /admin/exams
View all exams.

**Query Parameters:**
- status_f: Filter by status (optional)
- sel_faculty: Filter by faculty (optional)

**Response:** Renders exams page

---

### GET /admin/reports
View reports.

**Query Parameters:**
- sf: Filter by student (optional)
- ef: Filter by exam (optional)
- ff: Filter by faculty (optional)

**Response:** Renders reports page

---

### GET /admin/profile
View admin profile.

**Response:** Renders profile page

---

### POST /admin/change_password
Change admin password.

**Request Body:**
```json
{
  "current_password": "oldpass",
  "new_password": "newpass",
  "confirm_password": "newpass"
}
```

**Response:** Redirects with success or error message

---

## Common Endpoints

### GET /complete_profile
Complete user profile.

**Response:** Renders profile completion page

---

### POST /complete_profile
Submit profile completion.

**Request Body:**
- Profile fields based on user role

**Response:** Redirects to appropriate dashboard

---

## Error Responses

### 401 Unauthorized
User is not authenticated or lacks permission.

### 404 Not Found
Resource does not exist.

### 500 Internal Server Error
Server error occurred.

## Status Codes

- 200: Success
- 302: Redirect
- 400: Bad Request
- 401: Unauthorized
- 404: Not Found
- 500: Internal Server Error
