import React, { useState, useEffect } from 'react';
import {Input, Textarea, Button, Table, TableHeader, TableBody, TableColumn, TableRow, TableCell, Card} from "@nextui-org/react";
import ReactMarkdown from 'react-markdown';
import "./styles/globals.css";
interface Profile {
    linkedin_url: string;
    first_name: string;
    last_name: string;
    title: string;
}

interface Organization {
  id: string;
  name: string;
  linkedin_url?: string;
}

const App: React.FC = () => {
    const [orgName, setOrgName] = useState('');
    const [keyword, setKeyword] = useState('');
    const [profiles, setProfiles] = useState<Profile[]>([]);
    const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null);
    const [prompt, setPrompt] = useState('');
    const [output, setOutput] = useState('');
    const [organizations, setOrganizations] = useState<Organization[]>([]);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [formattedOutput, setFormattedOutput] = useState<React.ReactNode[]>([]);
    const [currentPage, setCurrentPage] = useState(1);

    const handleResponse = (response: Response, callback: (chunk: string) => void) => {
        const reader = response.body?.getReader();
        const decoder = new TextDecoder('utf-8');

        const processText = async (result: ReadableStreamReadResult<Uint8Array>): Promise<void> => {
            const { done, value } = result;
            if (done) return;
            const chunk = decoder.decode(value, { stream: true });
            callback(chunk);
            await reader?.read().then(processText);
        };

        reader?.read().then(processText);
    };

    const fetchOrgs = async () => {
        setOutput('');
        setOrganizations([]); // Clear existing organizations
        const response = await fetch('http://127.0.0.1:5000/api/get_orgs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ org_name: orgName })
        });

        handleResponse(response, (chunk) => {
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data.startsWith('Found') || data.startsWith('Searching')) {
                        setOutput(prev => prev + data + '\n');
                    } else {
                        try {
                            const orgs = JSON.parse(data);
                            setOrganizations(orgs); // Set all organizations
                            setOutput(prev => prev + JSON.stringify(orgs, null, 2) + '\n');
                        } catch (error) {
                            console.error('Error parsing JSON:', error);
                        }
                    }
                }
            }
        });
    };

    const fetchPeople = async () => {
        setOutput('Initiating search...\n');
        const response = await fetch('http://127.0.0.1:5000/api/get_people', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ org_id: selectedOrg?.id, person_titles: [keyword] })
        });

        handleResponse(response, (chunk) => {
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data.startsWith('Searching') || data.startsWith('Sending') || data.startsWith('Received') || data.startsWith('Found')) {
                        setOutput(prev => prev + data + '\n');
                    } else {
                        try {
                            const profiles = JSON.parse(data);
                            setProfiles(profiles);
                            setOutput(prev => prev + `Profiles set: ${profiles.length} profiles\n`);
                        } catch (error) {
                            console.error('Error parsing JSON:', error);
                            setOutput(prev => prev + `Error parsing profile data: ${error}\n`);
                        }
                    }
                }
            }
        });
    };

    const summarizeProfiles = async () => {
        setOutput('Summarizing profiles...\n');
        const linkedin_urls = profiles.map(profile => profile.linkedin_url);
        
        try {
            const response = await fetch('http://127.0.0.1:5000/api/summarize_profiles', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    linkedin_urls,
                    prompt,
                    company_name: selectedOrg?.name,
                    email,
                    password
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            // Update the output with just the JSON response
            setOutput(JSON.stringify(data, null, 2));
        } catch (error) {
            console.error('Error:', error);
            setOutput(prev => prev + `Error: ${error}\n`);
        }
    };

    const MarkdownOutput = ({ content }: { content: string }) => {
        return (
            <ReactMarkdown
                components={{
                    a: ({ node, ...props }) => (
                        <a
                            {...props}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline"
                        />
                    ),
                    p: ({ node, ...props }) => <p {...props} className="mb-4" />,
                    h1: ({ node, ...props }) => <h1 {...props} className="text-2xl font-bold mb-2" />,
                    h2: ({ node, ...props }) => <h2 {...props} className="text-xl font-bold mb-2" />,
                    h3: ({ node, ...props }) => <h3 {...props} className="text-lg font-bold mb-2" />,
                    ul: ({ node, ...props }) => <ul {...props} className="list-disc list-inside mb-4" />,
                    ol: ({ node, ...props }) => <ol {...props} className="list-decimal list-inside mb-4" />,
                    li: ({ node, ...props }) => <li {...props} className="mb-1" />,
                    strong: ({ node, ...props }) => <strong {...props} className="font-bold" />,
                    em: ({ node, ...props }) => <em {...props} className="italic" />,
                }}
            >
                {content}
            </ReactMarkdown>
        );
    };

    useEffect(() => {
        const formatOutput = () => {
            try {
                const outputData = JSON.parse(output);
                if (outputData.summary && outputData.citations) {
                    const citationRegex = /<(\d+\.\d+)>/g;
                    let formattedSummary = outputData.summary.replace(citationRegex, (_: string, p1: string) => {
                        const citation = outputData.citations[`<${p1}>`];
                        const [name] = citation.split(',');
                        const profile = profiles.find(p => p.first_name === name.split(' ')[1]);
                        return `[${p1}](${profile?.linkedin_url || '#'})`;
                    });
                    setFormattedOutput([<MarkdownOutput key="summary" content={formattedSummary} />]);
                } else {
                    setFormattedOutput([<MarkdownOutput key="output" content={output} />]);
                }
            } catch (error) {
                // If parsing fails, treat the output as plain text
                setFormattedOutput([<MarkdownOutput key="output" content={output} />]);
            }
        };

        formatOutput();
    }, [output, profiles]);

    const isStepComplete = (step: number) => {
        switch (step) {
            case 1:
                return selectedOrg !== null;
            case 2:
                return profiles.length > 0;
            case 3:
                return prompt !== '' && email !== '' && password !== '';
            default:
                return false;
        }
    };

    const handleNext = () => {
        if (currentPage < 3 && isStepComplete(currentPage)) {
            setCurrentPage(currentPage + 1);
        }
    };

    const handleBack = () => {
        if (currentPage > 1) {
            setCurrentPage(currentPage - 1);
        }
    };

    const renderStep = () => {
        switch (currentPage) {
            case 1:
                return (
                    <div className="space-y-8">
                        <div className="space-y-4">
                            <h2 className="text-2xl font-semibold mb-4">Search for Organizations</h2>
                            <div className="flex items-center space-x-4">
                                <Input
                                    type="text"
                                    value={orgName}
                                    onChange={e => setOrgName(e.target.value)}
                                    placeholder="Organization Name"
                                    className="flex-grow"
                                />
                                <Button color="primary" onClick={fetchOrgs}>Search</Button>
                            </div>
                        </div>
                        {organizations.length > 0 && (
                            <div className="space-y-4">
                                <h2 className="text-2xl font-semibold">All Organizations</h2>
                                <Table 
                                    aria-label="All Organizations"
                                    selectionMode="single"
                                    onSelectionChange={(keys) => {
                                        const selectedId = [...keys][0];
                                        const org = organizations.find(org => org.id === selectedId);
                                        setSelectedOrg(org || null);
                                    }}
                                >
                                    <TableHeader>
                                        <TableColumn>Name</TableColumn>
                                        <TableColumn>LinkedIn URL</TableColumn>
                                    </TableHeader>
                                    <TableBody items={organizations}>
                                        {(org) => (
                                            <TableRow key={org.id}>
                                                <TableCell>{org.name}</TableCell>
                                                <TableCell>
                                                    {org.linkedin_url ? (
                                                        <a
                                                            href={org.linkedin_url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-blue-500 hover:underline text-sm"
                                                            onClick={(e) => e.stopPropagation()}
                                                        >
                                                            LinkedIn
                                                        </a>
                                                    ) : (
                                                        <span className="text-gray-400 text-sm">No LinkedIn URL</span>
                                                    )}
                                                </TableCell>
                                            </TableRow>
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </div>
                );
            case 2:
                return (
                    <div className="space-y-8">
                        <div className="space-y-4">
                            <h2 className="text-2xl font-semibold">Search for People</h2>
                            <div className="flex items-center space-x-4">
                                <Input
                                    type="text"
                                    value={keyword}
                                    onChange={e => setKeyword(e.target.value)}
                                    placeholder="Keyword"
                                    className="flex-grow"
                                />
                                <Button onClick={fetchPeople} color='primary'>Search</Button>
                            </div>
                        </div>
                        {profiles.length > 0 && (
                            <div className="space-y-4">
                                <h2 className="text-2xl font-semibold">Found Profiles</h2>
                                <Table aria-label="Found Profiles">
                                    <TableHeader>
                                        <TableColumn>First Name</TableColumn>
                                        <TableColumn>Last Name</TableColumn>
                                        <TableColumn>Title</TableColumn>
                                        <TableColumn>LinkedIn URL</TableColumn>
                                    </TableHeader>
                                    <TableBody>
                                        {profiles.map((profile, index) => (
                                            <TableRow key={index}>
                                                <TableCell>{profile.first_name}</TableCell>
                                                <TableCell>{profile.last_name}</TableCell>
                                                <TableCell>{profile.title}</TableCell>
                                                <TableCell>
                                                    <a
                                                        href={profile.linkedin_url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-blue-500 hover:underline"
                                                    >
                                                        {profile.linkedin_url}
                                                    </a>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </div>
                );
            case 3:
                return (
                    <div className="space-y-8">
                        <div className="space-y-4">
                            <h2 className="text-2xl font-semibold">Summarize Profiles</h2>
                            <Input
                                type="email"
                                value={email}
                                onChange={e => setEmail(e.target.value)}
                                placeholder="LinkedIn Email"
                                className="w-full"
                            />
                            <Input
                                type="password"
                                value={password}
                                onChange={e => setPassword(e.target.value)}
                                placeholder="LinkedIn Password"
                                className="w-full"
                            />
                            <Textarea
                                value={prompt}
                                onChange={e => setPrompt(e.target.value)}
                                placeholder="Ask a question or provide a prompt..."
                                rows={3}
                                className="w-full"
                            />
                        </div>
                        <div className="flex justify-end">
                            <Button onClick={summarizeProfiles} color='primary'>Summarize</Button>
                        </div>
                        {output && (
                            <div className="mt-8">
                                <Card className="p-6">
                                    <h2 className="text-2xl font-semibold mb-6">Output</h2>
                                    <div className="p-6 rounded-lg whitespace-pre-wrap text-md">
                                        {formattedOutput}
                                    </div>
                                </Card>
                            </div>
                        )}
                    </div>
                );
            default:
                return null;
        }
    };

    return (
        <div className="min-h-screen flex flex-col py-8 px-4">
            <div className="max-w-4xl w-full mx-auto flex-grow flex flex-col">
                <h1 className="text-3xl font-bold mb-8 mt-8">LinkedIn Profile Management</h1>
                <div className="flex-grow flex flex-col space-y-8 mb-8">
                    {renderStep()}
                </div>
                <div className="flex justify-between mt-auto">
                    <Button 
                        onClick={handleBack}
                        variant="flat"
                        isDisabled={currentPage === 1}
                        color="primary"
                    >
                        Back
                    </Button>
                    <Button 
                        onClick={handleNext} 
                        variant="flat"
                        isDisabled={currentPage === 3 || !isStepComplete(currentPage)}
                        color="primary"
                    >
                        Next
                    </Button>
                </div>
            </div>
        </div>
    );
};

export default App;