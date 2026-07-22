# LMS Learning Platform - Functionality Guide

## Overview

LMS is a comprehensive learning management platform designed to facilitate online education, resource sharing, and community interaction. This document provides detailed information about all features and functionality available in the platform.

## 🎯 Core Features

### 1. User Management System

#### User Registration & Authentication
- **Secure Login/Logout**: Users can securely log in and out of the platform
- **Session Management**: Persistent sessions with automatic timeout
- **Password Security**: Passwords are hashed using industry-standard encryption
- **Tiered Admin Access**: Three access levels — full admin, sub-admin, and regular user (see Admin section)

#### User Profiles
- **Personal Information**: Username, email, and profile management
- **Course Enrollment**: Users can enroll in available courses
- **Activity Tracking**: System tracks user interactions and activities

### 2. Course Management

#### Course Catalog
- **Browse Courses**: Users can view all available courses
- **Course Details**: Comprehensive course information including:
  - Course title and description
  - Time slots and scheduling
  - Profile emojis for visual identification
- **Enrollment System**: Users can enroll in courses they're interested in

#### Course Content Management
- **Content Modules**: Organize course materials into modules and folders
- **File Management**: Upload and organize course files (videos, documents, etc.)
- **Content Folders**: Hierarchical folder structure for course organization
- **Content Ordering**: Custom ordering of course materials
- **Access Control**: Control content visibility based on enrollment and progress

#### Assignments & Submissions
- **Assignment Creation**: Teachers can create assignments with due dates and points
- **File Submissions**: Students can submit assignments via file upload
- **Google Drive Integration**: Seamless file storage and sharing
- **Grading System**: Teachers can grade submissions and provide feedback
- **Submission Tracking**: Track submission status and deadlines

#### Course Announcements
- **Announcement System**: Teachers can post course-wide announcements
- **Threaded Discussions**: Students can reply to announcements
- **Real-time Updates**: Keep students informed of important updates
- **Announcement Management**: Edit and manage course communications

#### Course Reviews
- **Student Feedback**: Enrolled students can leave reviews and ratings
- **Rating System**: 1-5 star rating system for courses
- **Review Management**: Teachers and admins can moderate reviews
- **Analytics**: Track course satisfaction and improvement areas

#### Course Administration (Admin Only)
- **Create/Edit Courses**: Administrators can add new courses or modify existing ones
- **User Management**: Assign users to courses and manage enrollments
- **Content Management**: Full control over course materials and structure
- **Course Analytics**: Track enrollment, completion, and engagement metrics

### 3. Resource Library

#### Learning Resources
- **Resource Upload**: Users can upload learning materials and documents
- **PIN Protection**: Resources are protected with access PINs for security
- **File Management**: Support for various file types and secure storage
- **Access Control**: Uploaders can view their own resource PINs

#### Resource Administration
- **Admin Oversight**: Administrators can manage all resources
- **Content Moderation**: Review and approve uploaded resources
- **File Organization**: Categorize and organize learning materials

### 4. PDF Document Management

#### Secure PDF Library
- **PDF Upload**: Secure upload system for PDF documents
- **PIN-Based Access**: Each PDF is protected with a unique access PIN
- **File Security**: Encrypted storage and secure access controls
- **Document Tracking**: Track upload dates, file sizes, and access patterns

#### PDF Features
- **Uploader Visibility**: Uploaders can see their document PINs
- **Admin Management**: Complete administrative control over PDF documents
- **File Validation**: Automatic PDF format validation during upload

### 5. Google Drive Integration

#### File Storage
- **Cloud Storage**: All uploaded files stored securely in Google Drive
- **Access Control**: Granular permissions for file sharing and access
- **File Management**: Upload, download, and organize files through Google Drive API
- **Link Generation**: Automatic generation of view and download links

#### Integration Features
- **Seamless Uploads**: Direct upload to Google Drive without local storage
- **File Permissions**: Set appropriate sharing permissions for different user types
- **Batch Operations**: Handle multiple file operations efficiently
- **Error Handling**: Robust error recovery for upload and access failures

### 6. Background Job Processing

#### Asynchronous Tasks
- **Translation Jobs**: AI-powered content translation in the background
- **File Processing**: Large file uploads and processing without blocking UI
- **Batch Operations**: Handle bulk operations asynchronously
- **Job Monitoring**: Track job progress and status in real-time

#### Job Management
- **Queue System**: Organize and prioritize background tasks
- **Status Tracking**: Monitor job completion and handle failures
- **Retry Logic**: Automatic retry for failed operations
- **Resource Management**: Efficient use of system resources for background processing

### 5. Community Forum

#### Discussion Platform
- **Threaded Discussions**: Create and participate in forum discussions
- **Message Hierarchy**: Support for main posts and threaded replies
- **Real-time Updates**: Dynamic forum content loading
- **User Attribution**: Messages are attributed to specific users
- **Channel-Based Organization**: Forum is organized into multiple channels with different access levels

#### Forum Channels
- **Public Channels**: Accessible to all users without login
- **Login-Required Channels**: Require user authentication to access
- **Admin-Only Channels**: Restricted to administrators only for private staff discussions
- **Channel Management**: Administrators can create, edit, and manage forum channels
- **Customizable Display Order**: Channels can be ordered using sort_order field

#### Forum Management
- **Content Moderation**: Administrators can moderate forum content
- **Message Editing**: Users can edit their own messages
- **Message Deletion**: Appropriate deletion permissions for users and admins
- **Channel Administration**: Full CRUD operations for forum channels
- **Spam Prevention**: Built-in measures to prevent forum abuse

### 6. Administrative Dashboard

#### Admin Permission Tiers

The admin system has three levels:

| Level | Condition | Access |
|---|---|---|
| **Full admin** | `is_admin=True`, no restrictions | All sections + Permissions management page |
| **Sub-admin** | `is_admin=True`, specific permissions assigned | Only their assigned sections |
| **Regular user** | `is_admin=False` | No admin access whatsoever |

Sub-admins can only be created from users who already have `is_admin=True`. Regular users cannot be given sub-admin features.

#### Admin Sections and Their Permission Keys

| Section | Permission key | What it covers |
|---|---|---|
| User Management | `user_management` | User list, create/edit/delete users |
| Course Management | `course_management` | Course CRUD, page builder, analytics |
| Certificate Management | `certificate_management` | Certificate overlay tuning |
| Forum Management | `forum_management` | Forum channels and messages |
| Builder Management | `builder_management` | Home page editor, About Company, content translation |
| Moxo Test Management | `moxo_test_management` | MOXO test results |
| Resource Management | `resource_management` | Learning resource library |
| Limitations Management | `limitations_management` | Page access restrictions |

#### Managing Permissions

Full admins can manage permissions at `/admin/user_permissions/`. Each admin user's row shows checkboxes for all 8 permissions. Checking all boxes restores full admin status (removes restrictions). Sub-admins cannot access the Permissions page.

To promote a user to full admin via CLI:
```bash
just make-admin <username>   # dev
# or on the server: scripts/admin/make_full_admin.py <username>
```

#### Security Features
- **Tiered Access Control**: Sub-admins only see sidebar items they have permission for; direct URL access is also blocked
- **Full admin gate on Permissions page**: Only `is_full_admin` users (unrestricted) can assign permissions to others
- **Audit Logging**: Track administrative actions
- **Secure Authentication**: Multi-factor authentication support ready

## 🔧 Technical Functionality

### API Architecture

#### RESTful Endpoints
- **Authentication API**: `/api/user`, `/login`, `/logout`
- **Course API**: `/api/courses`
- **Resource API**: `/api/resources`, `/api/resources/{id}/access`
- **PDF API**: `/api/pdfs`, `/api/pdfs/upload`
- **Forum API**: `/api/forum/messages`, `/api/forum/messages/{id}`

#### API Features
- **JSON Responses**: All API endpoints return structured JSON data
- **Error Handling**: Comprehensive error responses with appropriate HTTP status codes
- **Authentication**: Token-based authentication for API access
- **CORS Support**: Cross-origin resource sharing enabled

### File Upload System

#### Security Measures
- **File Type Validation**: Strict validation of uploaded file types
- **Size Limits**: Configurable file size restrictions
- **Path Security**: Secure file path handling to prevent directory traversal
- **Storage Organization**: Organized file storage with user-specific directories

#### Upload Features
- **Progress Tracking**: Real-time upload progress indicators
- **Error Recovery**: Robust error handling for failed uploads
- **Duplicate Prevention**: Mechanisms to prevent duplicate file uploads

### Internationalization (i18n)

#### Language Support
- **English**: Complete English language support
- **Azerbaijani**: Full Azerbaijani language localization
- **Russian**: Full Russian language localization
- **Dynamic Switching**: Real-time language switching without page reload
- **AI-Powered Translation**: Automatic content translation using machine learning
- **Translation Management**: Centralized translation file management

#### Localization Features
- **Date Formatting**: Localized date and time display
- **Number Formatting**: Culture-appropriate number formatting
- **Text Direction**: Support for right-to-left languages (extensible)
- **Content Translation**: Dynamic translation of course content, resources, and UI elements

## 🎨 User Interface Features

### Responsive Design
- **Mobile-First**: Optimized for mobile devices
- **Tablet Support**: Responsive design for tablet devices
- **Desktop Experience**: Full-featured desktop interface
- **Touch-Friendly**: Touch-optimized controls for mobile users

### User Experience
- **Intuitive Navigation**: Clear and logical navigation structure
- **Visual Feedback**: Immediate feedback for user actions
- **Loading States**: Progress indicators for long-running operations
- **Error Messages**: User-friendly error messages and guidance

### Accessibility
- **Keyboard Navigation**: Full keyboard accessibility
- **Screen Reader Support**: Compatible with screen reading software
- **Color Contrast**: High contrast ratios for readability
- **Semantic HTML**: Proper semantic markup for assistive technologies

## 🔒 Security Implementation

### Authentication & Authorization
- **Secure Sessions**: HTTP-only, secure session cookies
- **Password Policies**: Strong password requirements and validation
- **Account Lockout**: Protection against brute force attacks
- **Session Timeout**: Automatic session expiration for security

### Data Protection
- **Input Validation**: Comprehensive input sanitization
- **SQL Injection Prevention**: Parameterized queries and ORM protection
- **XSS Protection**: Content Security Policy and input escaping
- **CSRF Protection**: Cross-site request forgery prevention

### File Security
- **Upload Validation**: Strict file type and content validation
- **Path Traversal Protection**: Secure file path handling
- **Access Control**: PIN-based and role-based file access
- **Storage Encryption**: Secure file storage practices

## 📊 Data Management

### Database Schema
- **User Model**: User accounts with authentication, profile data, and tiered admin access (`is_admin`, `admin_permissions` JSON for sub-admin permission lists)
- **Course Model**: Course information, enrollment relationships, and content management
- **CourseContent Model**: Individual course content items (videos, documents, text)
- **CourseContentFolder Model**: Hierarchical folder structure for course organization
- **CourseAssignment Model**: Assignment definitions with due dates and requirements
- **CourseAssignmentSubmission Model**: Student submissions with grading and feedback
- **CourseAnnouncement Model**: Course-wide announcements and communications
- **CourseAnnouncementReply Model**: Threaded discussions on announcements
- **CourseReview Model**: Student reviews and ratings for courses
- **Resource Model**: Learning resources with Google Drive integration and PIN protection
- **PDFDocument Model**: PDF files with secure access controls
- **ForumChannel Model**: Forum channels with tiered access control (public/login-required/admin-only)
- **ForumMessage Model**: Discussion forum with threaded replies
- **HomeContent Model**: Configurable home page content and settings
- **Translation Model**: AI-powered translation cache for dynamic content
- **ContentTranslation Model**: Translated content for courses, resources, and UI elements
- **BackgroundJob Model**: Asynchronous job processing and status tracking
- **AppSetting Model**: Application configuration and settings storage

### Data Relationships
- **Many-to-Many**: Users can enroll in multiple courses
- **One-to-Many**: Users can upload multiple resources and PDFs
- **Channel-Based**: Forum messages are organized by channels with different access levels
- **Hierarchical**: Forum messages support threaded discussions
- **Ownership**: Clear ownership relationships for uploaded content

## 🚀 Future Enhancements

### Planned Features
- **Advanced Analytics**: Detailed learning analytics and reporting
- **Video Content**: Support for video lectures and tutorials
- **Gamification**: Achievement system and progress tracking
- **Mobile App**: Native mobile applications for iOS and Android
- **Integration APIs**: Third-party integration capabilities

### Technical Improvements
- **Microservices**: Potential migration to microservices architecture
- **Caching**: Redis caching for improved performance
- **CDN**: Content delivery network for global performance
- **Real-time Features**: WebSocket support for live interactions

## 📈 Performance & Scalability

### Current Performance
- **Fast Loading**: Optimized for quick page loads
- **Efficient Queries**: Optimized database queries
- **Caching**: Browser caching for static assets
- **Compression**: Gzip compression for responses

### Scalability Considerations
- **Database Optimization**: Indexing and query optimization
- **File Storage**: Scalable file storage solutions
- **Load Balancing**: Ready for load balancer integration
- **CDN Ready**: Prepared for content delivery networks

## 🐛 Troubleshooting

### Common Issues
- **Login Problems**: Check credentials and session settings
- **Upload Failures**: Verify file types and size limits
- **Forum Issues**: Check user permissions and content policies
- **Admin Access**: Ensure proper admin role assignment

### Debug Information
- **Error Logs**: Comprehensive logging for troubleshooting
- **API Debugging**: Detailed API response information
- **Performance Monitoring**: Built-in performance tracking
- **User Activity Logs**: Audit trails for security and debugging

## 📞 Support & Maintenance

### System Monitoring
- **Health Checks**: Automated system health monitoring
- **Performance Metrics**: Real-time performance tracking
- **Error Reporting**: Automated error notification
- **Backup Systems**: Regular data backup procedures

### Maintenance Procedures
- **Database Maintenance**: Regular database optimization
- **Security Updates**: Timely security patch application
- **Performance Tuning**: Ongoing performance optimization
- **User Support**: Comprehensive user assistance systems

---

This functionality guide provides a comprehensive overview of the LMS learning platform. For technical implementation details, see the main README.md file.